import os
import uuid
import json
from datetime import datetime, timezone
import time
import random
from . import config 
from .common.logging_utils import setup_logger

# Initialize logger for this module using the level from config
logger = setup_logger(__name__, level_str=config.LOG_LEVEL)


def create_event(): # Modified function
    now = datetime.now(timezone.utc)
    event_id = str(uuid.uuid4())
    claim_id = f"C-{now.year}{random.randint(10000, 99999)}"
    policy_id = f"P-{random.getrandbits(32):08x}"
    loss_type = random.choice(["collision", "theft", "injury", "vandalism", "other", "fire"])
    amount = round(random.uniform(100, 75000), 2) # Increased max amount slightly
    days_since_policy_start = random.randint(0, 3650) # Allow 0 days for new policy claims
    is_total_loss = random.choice([True, False, False, False]) # Make total loss a bit less common

    # --- Rule-based FraudFound_P ---
    fraud_chance = 0.05 # Base chance of fraud
    
    # Rule 1: Higher chance of fraud for very new policies with high amounts
    if days_since_policy_start < 30 and amount > 20000:
        fraud_chance += 0.40
        
    # Rule 2: Higher chance for certain loss types if amount is large
    if loss_type in ["theft", "fire"] and amount > 30000:
        fraud_chance += 0.30
        
    # Rule 3: Total loss claims might have a slightly higher chance
    if is_total_loss and amount > 15000:
        fraud_chance += 0.15

    # Rule 4: Very small claims are less likely to be sophisticated fraud (for this example)
    if amount < 500:
        fraud_chance -= 0.03

    # Ensure fraud_chance is within reasonable bounds (e.g., 0 to 0.9)
    fraud_chance = max(0.01, min(fraud_chance, 0.9)) 
    
    is_fraud = random.random() < fraud_chance
    # --- End Rule-based FraudFound_P ---

    return {
        "event_id": event_id,
        "event_ts": now.isoformat(),
        "claim_id": claim_id,
        "policy_id": policy_id,
        "loss_type": loss_type,
        "amount": amount,
        "days_since_policy_start": days_since_policy_start,
        "is_total_loss": is_total_loss,
        "FraudFound_P": 1 if is_fraud else 0 # Ensure it's 0 or 1
    }

def run_generator():
    logger.info("Initializing data generator...")
    logger.info(f"Raw data will be saved to directory: {config.RAW_DATA_PATH}")
    logger.info(f"Generation interval: {config.GENERATOR_SLEEP_MIN_SECONDS}-{config.GENERATOR_SLEEP_MAX_SECONDS} seconds")

    try:
        # config.RAW_DATA_PATH is already an absolute path
        os.makedirs(config.RAW_DATA_PATH, exist_ok=True)
    except OSError as e:
        logger.error(f"Error creating raw data base directory {config.RAW_DATA_PATH}: {e}")
        return 

    try:
        while True:
            today_dir_name = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            today_full_path = os.path.join(config.RAW_DATA_PATH, today_dir_name)
            
            try:
                os.makedirs(today_full_path, exist_ok=True)
            except OSError as e:
                logger.error(f"Error creating daily directory {today_full_path}: {e}")
                time.sleep(60) 
                continue

            event = create_event()
            out_path = os.path.join(today_full_path, f"{event['event_id']}.json")
            
            try:
                with open(out_path, "w") as f:
                    json.dump(event, f, indent=2)
                logger.info(f"Generated event -> {out_path}")
            except IOError as e:
                logger.error(f"Error writing event to file {out_path}: {e}")
            
            sleep_duration = random.randint(
                config.GENERATOR_SLEEP_MIN_SECONDS, 
                config.GENERATOR_SLEEP_MAX_SECONDS
            )
            time.sleep(sleep_duration)
            
    except KeyboardInterrupt:
        logger.info("Synthetic data generation stopped by user.")
    except Exception as e:
        logger.critical(f"An unexpected error occurred in the generator: {e}", exc_info=True)
    finally:
        logger.info("Generator shutdown.")

if __name__ == "__main__":
    run_generator()