import os
import sys
import config
from common.logging_utils import setup_logger
import json
import time
import pandas as pd
from confluent_kafka import Consumer, KafkaError, KafkaException
from datetime import datetime, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__)) # Gets /opt/airflow/project_flows/
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR) # Add current script's directory (project_flows)

# module_logger = setup_logger(__name__, level_str=config.LOG_LEVEL) # Optional

def process_and_save_silver_batch(message_payloads: list, processing_timestamp_iso: str, base_logger_name: str) -> int:
    logger = setup_logger(f"{base_logger_name}.process_save_batch", level_str=config.LOG_LEVEL)
    if not message_payloads:
        logger.info("No message payloads to process for silver batch.")
        return 0
    df = pd.DataFrame(message_payloads)
    logger.debug(f"Created DataFrame with {len(df)} rows from batch.")
    if df.empty:
        logger.info("DataFrame is empty. Nothing to save to silver.")
        return 0
    if "event_id" in df.columns:
        rows_before_dedupe = len(df)
        df.drop_duplicates(subset=["event_id"], keep="first", inplace=True)
        if len(df) < rows_before_dedupe:
            logger.info(f"Dropped {rows_before_dedupe - len(df)} duplicate event_ids within the batch.")
    else:
        logger.warning("'event_id' column not found in batch data. Cannot deduplicate effectively.")
    if "event_ts" in df.columns:
        df["event_ts"] = pd.to_datetime(df["event_ts"], errors='coerce')
    else:
        logger.warning("'event_ts' column not found.")
    df["processing_date_str"] = pd.to_datetime(processing_timestamp_iso).strftime('%Y-%m-%d')
    if df.empty:
        logger.info("DataFrame is empty after cleaning/deduplication. Nothing to save.")
        return 0
    rows_saved_total = 0
    try:
        partition_col_name = "processing_date_str" 
        unique_file_id = f"silver_data_{int(time.time() * 1000000)}_{os.getpid()}.parquet" 
        date_str_partition_value = df[partition_col_name].iloc[0]
        partition_dir_path = os.path.join(config.SILVER_DATA_PATH, f"{partition_col_name}={date_str_partition_value}")
        os.makedirs(partition_dir_path, exist_ok=True)
        output_file_path = os.path.join(partition_dir_path, unique_file_id)
        group_df_to_save = df.copy()
        if partition_col_name in group_df_to_save.columns:
             group_df_to_save.drop(columns=[partition_col_name], inplace=True)
        if group_df_to_save.empty:
            logger.info(f"Data for partition {date_str_partition_value} is empty. Skipping save for this group.")
        else:
            group_df_to_save.to_parquet(output_file_path, index=False, engine='pyarrow')
            rows_saved_total = len(group_df_to_save)
            logger.info(f"Saved {rows_saved_total} rows to Silver Parquet: {output_file_path}")
        return rows_saved_total
    except Exception as e:
        logger.error(f"Error saving batch to Parquet: {e}", exc_info=True)
        raise 

def run_silver_batch_once():
    logger = setup_logger(f"{__name__}.run_silver_batch_once", level_str=config.LOG_LEVEL) 
    logger.info("Starting Silver layer batch processing run...")

    consumer_conf = {
        'bootstrap.servers': config.KAFKA_BOOTSTRAP_SERVERS, 
        'group.id': config.KAFKA_SILVER_CONSUMER_GROUP,
        'auto.offset.reset': 'earliest',
        'enable.auto.commit': False, 
    }
    consumer = None 
    try:
        consumer = Consumer(consumer_conf)
        consumer.subscribe([config.KAFKA_RAW_TOPIC])
        logger.info(f"Subscribed to Kafka topic: {config.KAFKA_RAW_TOPIC}")
        os.makedirs(config.SILVER_DATA_PATH, exist_ok=True)
        raw_kafka_messages_batch = []
        message_payloads_batch = []
        start_poll_time = time.time()
        while (len(raw_kafka_messages_batch) < config.SILVER_BATCH_SIZE and \
               time.time() - start_poll_time < config.SILVER_BATCH_TIMEOUT_SECONDS): 
            msg = consumer.poll(timeout=1.0) 
            if msg is None: 
                if raw_kafka_messages_batch: 
                    logger.debug("Poll timeout, but batch has messages. Continuing poll briefly or will process current batch.")
                else: 
                    if time.time() - start_poll_time > 5 : 
                       logger.info("No messages found after initial polling period for this batch run.")
                       break 
                continue 
            if msg.error():
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    logger.debug(f"Reached end of partition: {msg.topic()}/{msg.partition()} at offset {msg.offset()}")
                    continue 
                else: 
                    logger.error(f"Kafka error while polling: {msg.error()}")
                    raise KafkaException(msg.error())
            else:
                raw_kafka_messages_batch.append(msg)
                try:
                    payload = json.loads(msg.value().decode('utf-8'))
                    message_payloads_batch.append(payload)
                except Exception as e: 
                    logger.error(f"Error decoding message (offset {msg.offset()}): {e}. Value(hex): {msg.value().hex()[:100]}", exc_info=True)
        if raw_kafka_messages_batch and message_payloads_batch:
            logger.info(f"Collected {len(raw_kafka_messages_batch)} raw Kafka messages, resulting in {len(message_payloads_batch)} decoded payloads.")
            processing_timestamp_for_this_batch = datetime.now(timezone.utc).isoformat()
            rows_saved = process_and_save_silver_batch(message_payloads_batch, processing_timestamp_for_this_batch, __name__)
            consumer.commit(message=raw_kafka_messages_batch[-1], asynchronous=False)
            logger.info(f"Committed Kafka offsets up to offset {raw_kafka_messages_batch[-1].offset()}. Saved {rows_saved} rows to Silver this batch.")
        elif raw_kafka_messages_batch and not message_payloads_batch:
            logger.warning("Collected raw Kafka messages, but none could be decoded into valid payloads. Committing to advance past these messages.")
            consumer.commit(message=raw_kafka_messages_batch[-1], asynchronous=False)
        else:
            logger.info("No messages collected from Kafka in this run to process for Silver.")
    except KafkaException as e: 
        logger.error(f"KafkaException in Silver processing run: {e}", exc_info=True)
        raise 
    except Exception as e: 
        logger.critical(f"Unexpected error in Silver processing run: {e}", exc_info=True)
        raise 
    finally:
        if consumer:
            consumer.close()
            logger.info("Kafka consumer closed.")
        logger.info("Silver layer batch processing run finished.")

if __name__ == "__main__":  
    main_run_logger = setup_logger("silver_processor_main_direct_run", level_str=config.LOG_LEVEL if 'config' in globals() else None)
    main_run_logger.info("Silver processor script executed directly for a single batch run.")
    try:
        run_silver_batch_once()
    except Exception as e:
        main_run_logger.critical(f"Direct run of silver_processor failed: {e}", exc_info=True)