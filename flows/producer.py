import os
import json
import time
from datetime import datetime, timezone
import glob
import shutil
from confluent_kafka import Producer, KafkaException
from . import config
from .common.logging_utils import setup_logger

logger = setup_logger(__name__, level_str=config.LOG_LEVEL)

def delivery_report(err, msg):
    """ Called once for each message produced to indicate delivery result. """
    if err is not None:
        # Ensure msg.key() is decoded if it's bytes, or handle None
        key_str = msg.key().decode('utf-8') if msg.key() else 'N/A'
        logger.error(f"Message delivery failed for key '{key_str}': {err}")
    else:
        logger.debug(f"Message delivered to {msg.topic()} [{msg.partition()}] @ offset {msg.offset()}")

def run_producer():
    logger.info("Initializing Kafka producer...")
    producer_conf = {
        "bootstrap.servers": config.KAFKA_BOOTSTRAP_SERVERS, # Uses smart value from config.py
        "acks": "all",
        "retries": 3,
        "retry.backoff.ms": 1000
    }
    
    try:
        producer = Producer(producer_conf)
    except KafkaException as e:
        logger.critical(f"Failed to create Kafka producer: {e}", exc_info=True)
        return
    except Exception as e:
        logger.critical(f"Unexpected error creating Kafka producer: {e}", exc_info=True)
        return

    logger.info(f"Kafka producer configured for servers: {config.KAFKA_BOOTSTRAP_SERVERS}")
    logger.info(f"Watching for files in: {config.PRODUCER_RAW_DATA_PATH}")
    logger.info(f"Processed files will be moved to: {config.PROCESSED_RAW_DATA_PATH}")
    logger.info(f"Producing to Kafka topic: {config.KAFKA_RAW_TOPIC}")

    try:
        # config paths are already absolute
        os.makedirs(config.PRODUCER_RAW_DATA_PATH, exist_ok=True)
        os.makedirs(config.PROCESSED_RAW_DATA_PATH, exist_ok=True)
    except OSError as e:
        logger.error(f"Error creating data directories: {e}")
        return

    processed_files_today_cache = set() # Simple in-memory cache for the current run

    try:
        while True:
            today_date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            current_day_raw_path = os.path.join(config.PRODUCER_RAW_DATA_PATH, today_date_str)
            current_day_processed_path = os.path.join(config.PROCESSED_RAW_DATA_PATH, today_date_str)

            if not os.path.exists(current_day_raw_path):
                logger.debug(f"Raw data directory for {today_date_str} not found. Polling...")
                time.sleep(config.PRODUCER_POLLING_INTERVAL_SECONDS)
                processed_files_today_cache.clear() 
                continue
            
            try:
                os.makedirs(current_day_processed_path, exist_ok=True)
            except OSError as e:
                logger.error(f"Error creating processed data directory for {today_date_str}: {e}")
                time.sleep(config.PRODUCER_POLLING_INTERVAL_SECONDS) # Wait before retrying
                continue
                
            found_files_this_cycle = False
            # Process in sorted order, e.g., by filename which might imply chronological order
            json_files = sorted(glob.glob(os.path.join(current_day_raw_path, "*.json")))

            for json_file_path in json_files:
                file_basename = os.path.basename(json_file_path)
                if file_basename in processed_files_today_cache: # Avoid reprocessing if script restarts quickly
                    continue

                found_files_this_cycle = True
                logger.debug(f"Found raw file: {json_file_path}")
                
                try:
                    with open(json_file_path, "r") as f:
                        data = json.load(f)
                    
                    event_id = data.get("event_id") # Use event_id as key for Kafka partitioning
                    
                    producer.produce(
                        config.KAFKA_RAW_TOPIC, 
                        json.dumps(data).encode('utf-8'), 
                        key=event_id.encode('utf-8') if event_id else None,
                        callback=delivery_report
                    )
                    
                    target_processed_file_path = os.path.join(current_day_processed_path, file_basename)
                    shutil.move(json_file_path, target_processed_file_path)
                    logger.info(f"Produced and moved to archive: {target_processed_file_path}")
                    processed_files_today_cache.add(file_basename)

                except json.JSONDecodeError as e:
                    logger.error(f"Error decoding JSON from {json_file_path}: {e}. Consider moving to an error directory.")
                except KafkaException as e: # If Kafka itself has an issue producing this message
                    logger.error(f"Kafka error producing message from {json_file_path}: {e}")
                    break
                except IOError as e:
                    logger.error(f"File IO error with {json_file_path}: {e}")
                except Exception as e:
                    logger.error(f"Unexpected error processing file {json_file_path}: {e}", exc_info=True)
            
            num_outstanding = producer.poll(0) # Non-blocking poll for delivery reports
            if num_outstanding > 0:
                logger.debug(f"{num_outstanding} messages in Kafka producer queue.")

            if not found_files_this_cycle:
                logger.debug(f"No new files found in {current_day_raw_path}. Sleeping.")
            
            time.sleep(config.PRODUCER_POLLING_INTERVAL_SECONDS)

    except KeyboardInterrupt:
        logger.info("Kafka producer stopping due to user interrupt.")
    except Exception as e:
        logger.critical(f"An unexpected error occurred in the producer main loop: {e}", exc_info=True)
    finally:
        logger.info("Flushing final messages from producer...")
        try:
            # Wait up to 30 seconds for all outstanding messages to be delivered
            producer.flush(30) 
            logger.info("All messages flushed.")
        except KafkaException as e: # Catch Kafka specific exceptions during flush
            logger.error(f"Error during final flush (KafkaException): {e}")
        except Exception as e: # Catch any other exception during flush
            logger.error(f"Unexpected error during final flush: {e}", exc_info=True)
        logger.info("Producer shutdown.")

if __name__ == "__main__":
    run_producer()