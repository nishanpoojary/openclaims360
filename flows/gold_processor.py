import os
import sys
import pandas as pd 
import duckdb
import glob
import config
from common.logging_utils import setup_logger

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__)) 
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR) 

# module_logger = setup_logger(__name__, level_str=config.LOG_LEVEL) # Optional module-level logger

def load_all_silver_data() -> pd.DataFrame:
    """
    Loads all Parquet files from the Silver data directory,
    concatenates them, and handles potential empty data.
    """
    logger = setup_logger(f"{__name__}.load_all_silver_data", level_str=config.LOG_LEVEL)
    
    # config.SILVER_DATA_PATH is already an absolute path
    silver_path_pattern = os.path.join(config.SILVER_DATA_PATH, "**", "*.parquet")
    # Using glob to find all parquet files in all subdirectories (e.g., date partitions)
    all_silver_files = glob.glob(silver_path_pattern, recursive=True)

    if not all_silver_files:
        logger.warning(f"No Silver Parquet files found matching pattern: {silver_path_pattern}")
        return pd.DataFrame()

    logger.info(f"Found {len(all_silver_files)} Silver Parquet files to load.")
    
    df_list = []
    for file_path in all_silver_files:
        try:
            df = pd.read_parquet(file_path, engine='pyarrow')
            df_list.append(df)
            logger.debug(f"Successfully loaded {len(df)} rows from: {file_path}")
        except Exception as e:
            logger.error(f"Error loading Silver Parquet file {file_path}: {e}", exc_info=True)
            # Continue to try loading other files, or re-raise if one bad file should stop all
            
    if not df_list:
        logger.warning("No data loaded from any Silver files (all might have been empty or errored).")
        return pd.DataFrame()
        
    full_silver_df = pd.concat(df_list, ignore_index=True)
    logger.info(f"Concatenated all Silver data into a DataFrame with {len(full_silver_df)} rows.")

    # Deduplication across all loaded silver files, if 'event_id' exists
    if "event_id" in full_silver_df.columns and not full_silver_df.empty:
        original_rows = len(full_silver_df)
        full_silver_df.drop_duplicates(subset=["event_id"], keep="last", inplace=True) # 'last' to keep latest if any reprocessing
        if len(full_silver_df) < original_rows:
            logger.info(f"Dropped {original_rows - len(full_silver_df)} duplicate event_ids from combined Silver data.")
    
    return full_silver_df

def engineer_features_for_gold(df: pd.DataFrame) -> pd.DataFrame:
    logger = setup_logger(f"{__name__}.engineer_features_for_gold", level_str=config.LOG_LEVEL)
    if df.empty:
        logger.info("Input DataFrame for feature engineering is empty. Skipping.")
        return df

    logger.info(f"Starting feature engineering on {len(df)} rows for Gold layer.")
    df_gold = df.copy()

    # 1. loss_type_cat (as before)
    if "loss_type" in df_gold.columns:
        try:
            df_gold["loss_type_cat"] = df_gold["loss_type"].astype("category").cat.codes
            logger.info("Engineered 'loss_type_cat' from 'loss_type'.")
        except Exception as e:
            logger.warning(f"Could not create 'loss_type_cat': {e}", exc_info=True)
    else:
        logger.warning("'loss_type' column not found for category encoding.")

    # 2. Amount per day since policy start (handle division by zero if days_since_policy_start can be 0)
    if "amount" in df_gold.columns and "days_since_policy_start" in df_gold.columns:
        # Add 1 to days_since_policy_start to avoid division by zero for brand new policies (0 days)
        df_gold["amount_per_day_on_policy"] = df_gold["amount"] / (df_gold["days_since_policy_start"] + 1)
        logger.info("Engineered 'amount_per_day_on_policy'.")

    # 3. Boolean for very new policy
    if "days_since_policy_start" in df_gold.columns:
        df_gold["is_very_new_policy"] = (df_gold["days_since_policy_start"] < 30).astype(int) # 0 or 1
        logger.info("Engineered 'is_very_new_policy'.")

    # 4. Interaction: High amount on new policy
    if "amount" in df_gold.columns and "is_very_new_policy" in df_gold.columns:
        df_gold["high_amount_on_new_policy"] = ((df_gold["amount"] > 20000) & (df_gold["is_very_new_policy"] == 1)).astype(int)
        logger.info("Engineered 'high_amount_on_new_policy'.")
        
    # 5. Extract features from event_ts (if it exists and is datetime)
    if "event_ts" in df_gold.columns and pd.api.types.is_datetime64_any_dtype(df_gold["event_ts"]):
        df_gold["event_month"] = df_gold["event_ts"].dt.month
        df_gold["event_day_of_week"] = df_gold["event_ts"].dt.dayofweek # Monday=0, Sunday=6
        df_gold["event_hour"] = df_gold["event_ts"].dt.hour
        logger.info("Engineered date/time features from 'event_ts': month, day_of_week, hour.")
    else:
        logger.warning("'event_ts' not found or not in datetime format for feature engineering.")
    
    logger.info(f"Finished feature engineering. DataFrame shape: {df_gold.shape}")
    logger.info(f"Columns in engineered Gold DF: {df_gold.columns.tolist()}")
    return df_gold

def save_to_gold_stores(df: pd.DataFrame):
    """
    Saves the transformed DataFrame to the Gold Parquet file and DuckDB.
    This function will overwrite existing Gold data.
    """
    logger = setup_logger(f"{__name__}.save_to_gold_stores", level_str=config.LOG_LEVEL)
    if df.empty:
        logger.warning("Gold DataFrame is empty. Nothing will be saved to Gold stores.")
        return

    # config.GOLD_DATA_PATH is already an absolute path
    os.makedirs(config.GOLD_DATA_PATH, exist_ok=True) 
    
    gold_parquet_full_path = os.path.join(config.GOLD_DATA_PATH, config.GOLD_PARQUET_FILENAME)
    duckdb_full_path = os.path.join(config.GOLD_DATA_PATH, config.DUCKDB_FILENAME)
    duckdb_table_name = config.DUCKDB_GOLD_TABLE_NAME

    # --- Save to Gold Parquet File ---
    try:
        df.to_parquet(gold_parquet_full_path, index=False, engine='pyarrow')
        logger.info(f"Successfully saved Gold data to Parquet: {gold_parquet_full_path} ({len(df)} rows)")
    except Exception as e:
        logger.error(f"Error saving Gold data to Parquet file {gold_parquet_full_path}: {e}", exc_info=True)
        raise # Re-raise to ensure Airflow task fails

    # --- Save to DuckDB ---
    try:
        logger.info(f"Attempting to save/replace DuckDB table '{duckdb_table_name}' in file: {duckdb_full_path}")
        with duckdb.connect(database=duckdb_full_path, read_only=False) as con:
            # Using read_parquet directly in SQL is often robust for DuckDB
            con.execute(f"CREATE OR REPLACE TABLE {duckdb_table_name} AS SELECT * FROM read_parquet('{gold_parquet_full_path}')")
            
            table_count_result = con.execute(f"SELECT COUNT(*) FROM {duckdb_table_name}").fetchone()
            if table_count_result:
                 logger.info(f"Successfully created/replaced table '{duckdb_table_name}' in DuckDB with {table_count_result[0]} rows.")
            else: 
                logger.warning(f"DuckDB table '{duckdb_table_name}' was created but count query failed or returned no result.")
    except Exception as e:
        logger.error(f"Error saving Gold data to DuckDB {duckdb_full_path}: {e}", exc_info=True)
        raise # Re-raise to ensure Airflow task fails

def run_gold_processing():
    """Main function to orchestrate Gold layer processing."""
    logger = setup_logger(f"{__name__}.run_gold_processing", level_str=config.LOG_LEVEL)
    logger.info("Starting Gold layer processing...")

    try:
        silver_df = load_all_silver_data()
        if silver_df.empty:
            logger.warning("No data loaded from Silver layer. Gold processing will terminate.")
            return

        gold_df_engineered = engineer_features_for_gold(silver_df)
        if gold_df_engineered.empty: 
            logger.warning("Data became empty after feature engineering. Gold processing will terminate.")
            return
            
        save_to_gold_stores(gold_df_engineered)
        logger.info("Gold layer processing finished successfully.")
    except Exception as e:
        logger.critical(f"Gold processing pipeline failed: {e}", exc_info=True)
        raise # Re-raise to ensure Airflow task fails if any step fails

if __name__ == "__main__":
    # Create a logger instance for this direct run context
    main_run_logger = setup_logger("gold_processor_main_direct_run", level_str=config.LOG_LEVEL)
    main_run_logger.info("Gold processor script executed directly.")
    try:
        run_gold_processing()
    except Exception as e:
        main_run_logger.critical(f"Direct run of gold_processor failed: {e}", exc_info=True)