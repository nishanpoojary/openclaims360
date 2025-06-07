import os
import sys
import pandas as pd
import numpy as np
import mlflow
import config
from common.logging_utils import setup_logger

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

logger = setup_logger(__name__, level_str=config.LOG_LEVEL)

# Path to the gold data (to simulate new, unseen data for this example)
GOLD_PARQUET_FULL_PATH = os.path.join(config.GOLD_DATA_PATH, config.GOLD_PARQUET_FILENAME)

# --- Function to simulate fetching new data ---
def get_new_data_for_prediction(sample_size=10) -> pd.DataFrame:
    """
    Simulates fetching new data. For this example, it loads the existing
    gold data, takes a sample, and drops the actual target variable.
    In a real scenario, this would fetch data from a new source (e.g., Kafka, DB).
    """
    logger.info(f"Simulating fetching new data from: {GOLD_PARQUET_FULL_PATH}")
    try:
        df_all_gold = pd.read_parquet(GOLD_PARQUET_FULL_PATH)
        if df_all_gold.empty:
            logger.warning("Gold data parquet is empty. Cannot generate sample data for prediction.")
            return pd.DataFrame()
        
        # Take a sample (ensure sample_size isn't larger than available data)
        num_rows = len(df_all_gold)
        actual_sample_size = min(sample_size, num_rows)
        if actual_sample_size == 0 :
            logger.warning("No data to sample from.")
            return pd.DataFrame()

        new_data_sample = df_all_gold.sample(n=actual_sample_size, random_state=np.random.randint(0,1000)) # Use random state for some variability
        
        # Drop the actual target variable if it exists, as the model will predict it
        if "FraudFound_P" in new_data_sample.columns:
            new_data_sample = new_data_sample.drop(columns=["FraudFound_P"])
            logger.info(f"Sampled {len(new_data_sample)} records and dropped 'FraudFound_P' for prediction.")
        else:
            logger.info(f"Sampled {len(new_data_sample)} records for prediction ('FraudFound_P' not present).")
            
        return new_data_sample
    except FileNotFoundError:
        logger.error(f"ERROR: Gold Parquet file not found at {GOLD_PARQUET_FULL_PATH} for sampling new data.")
        raise
    except Exception as e:
        logger.error(f"ERROR: Could not load Gold Parquet for sampling new data: {e}", exc_info=True)
        raise

# --- Feature Engineering ---
def engineer_features_for_prediction(df: pd.DataFrame) -> pd.DataFrame:
    """
    Performs IDENTICAL feature engineering as done during training.
    This function should mirror the logic in gold_processor.py's engineer_features_for_gold
    AND any feature prep done in train_model.py's prepare_data_for_model.
    """
    logger.info(f"Starting feature engineering for prediction on {len(df)} rows.")
    if df.empty:
        logger.warning("DataFrame for prediction feature engineering is empty.")
        return df

    df_pred_features = df.copy()

    # 1. loss_type_cat (from gold_processor.py)
    if "loss_type" in df_pred_features.columns:
        try:
            df_pred_features["loss_type_cat"] = df_pred_features["loss_type"].astype("category").cat.codes
            logger.info("Engineered 'loss_type_cat'.")
        except Exception as e:
            logger.warning(f"Could not create 'loss_type_cat' during prediction: {e}", exc_info=True)
            df_pred_features["loss_type_cat"] = -1 # Handle missing category code
    else:
        logger.warning("'loss_type' column not found for 'loss_type_cat' engineering.")
        df_pred_features["loss_type_cat"] = -1 # Default if original column missing

    # 2. Amount per day since policy start (from gold_processor.py)
    if "amount" in df_pred_features.columns and "days_since_policy_start" in df_pred_features.columns:
        df_pred_features["amount_per_day_on_policy"] = df_pred_features["amount"] / (df_pred_features["days_since_policy_start"] + 1)
        logger.info("Engineered 'amount_per_day_on_policy'.")
    else:
        logger.warning("Missing 'amount' or 'days_since_policy_start' for 'amount_per_day_on_policy'.")
        # Create with default if needed by model, e.g., 0 or mean from training
        if "amount_per_day_on_policy" not in df_pred_features.columns: df_pred_features["amount_per_day_on_policy"] = 0


    # 3. Boolean for very new policy (from gold_processor.py)
    if "days_since_policy_start" in df_pred_features.columns:
        df_pred_features["is_very_new_policy"] = (df_pred_features["days_since_policy_start"] < 30).astype(int)
        logger.info("Engineered 'is_very_new_policy'.")
    else:
        logger.warning("Missing 'days_since_policy_start' for 'is_very_new_policy'.")
        if "is_very_new_policy" not in df_pred_features.columns: df_pred_features["is_very_new_policy"] = 0


    # 4. Interaction: High amount on new policy (from gold_processor.py)
    if "amount" in df_pred_features.columns and "is_very_new_policy" in df_pred_features.columns:
        df_pred_features["high_amount_on_new_policy"] = ((df_pred_features["amount"] > 20000) & (df_pred_features["is_very_new_policy"] == 1)).astype(int)
        logger.info("Engineered 'high_amount_on_new_policy'.")
    elif "high_amount_on_new_policy" not in df_pred_features.columns : # Ensure column exists if inputs missing
        logger.warning("Missing inputs for 'high_amount_on_new_policy'. Creating with default 0.")
        df_pred_features["high_amount_on_new_policy"] = 0


    # 5. Extract features from event_ts (from gold_processor.py)
    if "event_ts" in df_pred_features.columns:
        if not pd.api.types.is_datetime64_any_dtype(df_pred_features["event_ts"]):
             df_pred_features["event_ts"] = pd.to_datetime(df_pred_features["event_ts"], errors='coerce')
        
        if pd.api.types.is_datetime64_any_dtype(df_pred_features["event_ts"]):
            df_pred_features["event_month"] = df_pred_features["event_ts"].dt.month
            df_pred_features["event_day_of_week"] = df_pred_features["event_ts"].dt.dayofweek
            df_pred_features["event_hour"] = df_pred_features["event_ts"].dt.hour
            logger.info("Engineered date/time features from 'event_ts'.")
        else:
            logger.warning("'event_ts' could not be converted to datetime. Date features not created.")
            for col in ["event_month", "event_day_of_week", "event_hour"]: df_pred_features[col] = -1 # Default
    else:
        logger.warning("'event_ts' not found. Date features not created.")
        for col in ["event_month", "event_day_of_week", "event_hour"]: df_pred_features[col] = -1 # Default


    # --- Select and Order Features EXACTLY as in Training ---
    # This list must match 'actual_feature_cols' from train_model.py
    # And these features must have been created above or be present in input df
    expected_model_features = [
        'amount', 'days_since_policy_start', 'loss_type_cat',
        'amount_per_day_on_policy', 'is_very_new_policy',
        'high_amount_on_new_policy', 'event_month',
        'event_day_of_week', 'event_hour'
    ]
    
    for col in expected_model_features:
        if col not in df_pred_features.columns:
            logger.warning(f"Expected model feature '{col}' not found after engineering. Adding with default 0 or -1.")
            df_pred_features[col] = 0 if 'amount' in col else -1 # Simplified default
            
    # Handle NaNs in features (same way as in train_model.py)
    for col in expected_model_features:
        if df_pred_features[col].isnull().any():
            fill_value = df_pred_features[col].median() if pd.api.types.is_numeric_dtype(df_pred_features[col]) else df_pred_features[col].mode()[0] if not df_pred_features[col].mode().empty else 0
            df_pred_features[col].fillna(fill_value, inplace=True)
            logger.info(f"Filled NaN in feature '{col}' for prediction with '{fill_value}'.")

    logger.info(f"Final columns for prediction model: {expected_model_features}")
    try:
        df_model_input = df_pred_features[expected_model_features]
    except KeyError as e:
        logger.error(f"Missing expected model features after all processing: {e}. Available columns: {df_pred_features.columns.tolist()}")
        raise
        
    logger.info(f"Finished feature engineering for prediction. Shape for model: {df_model_input.shape}")
    return df_model_input

def run_predictions(mlflow_run_id: str, sample_data: pd.DataFrame = None):
    logger.info(f"Starting prediction process...")
    logger.info(f"Using MLflow Run ID: {mlflow_run_id} to load the model.")
    logger.info(f"MLflow Tracking URI: {config.MLFLOW_TRACKING_URI}")
    logger.info(f"MLflow Experiment: {config.MLFLOW_EXPERIMENT_NAME}")

    # Set MLflow Tracking URI (config.py handles context for local vs. Docker)
    try:
        mlflow.set_tracking_uri(config.MLFLOW_TRACKING_URI)
        mlflow.set_experiment(config.MLFLOW_EXPERIMENT_NAME) # Ensure experiment context is set
    except Exception as e:
        logger.error(f"Failed to set MLflow tracking URI or experiment: {e}", exc_info=True)

    # --- Load Model from MLflow ---
    # The model was logged with artifact_path="lgbm_fraud_model"
    model_uri = f"runs:/{mlflow_run_id}/lgbm_fraud_model"
    try:
        logger.info(f"Loading model from MLflow URI: {model_uri}")
        loaded_model = mlflow.pyfunc.load_model(model_uri) # pyfunc for generic interface
        logger.info("Model loaded successfully from MLflow.")
    except Exception as e:
        logger.error(f"Failed to load model from MLflow URI '{model_uri}': {e}", exc_info=True)
        return

    # --- Get and Prepare Data for Prediction ---
    if sample_data is None:
        new_data = get_new_data_for_prediction(sample_size=5) # Get 5 new samples
    else:
        new_data = sample_data.copy() # Use provided data

    if new_data.empty:
        logger.warning("No new data to make predictions on.")
        return

    # Keep original event_ids or other identifiers if present, for joining predictions back
    identifiers = None
    if "event_id" in new_data.columns:
        identifiers = new_data[["event_id"]].copy()
    
    # Prepare features for the model
    data_for_model_input = engineer_features_for_prediction(new_data)

    if data_for_model_input.empty:
        logger.warning("Data became empty after feature engineering for prediction. No predictions will be made.")
        return

    # --- Make Predictions ---
    try:
        logger.info(f"Making predictions on {len(data_for_model_input)} records...")
        predictions_proba = loaded_model.predict(data_for_model_input) # For pyfunc model, usually gives probability of positive class or direct prediction
        
        final_predictions = []
        if hasattr(loaded_model._model_impl, 'predict_proba'): # Check if it's an sklearn-like model
            fraud_probabilities = loaded_model._model_impl.predict_proba(data_for_model_input)[:, 1]
            predicted_classes = (fraud_probabilities >= 0.5).astype(int) # Example threshold
            for i in range(len(data_for_model_input)):
                final_predictions.append({
                    "input_features": data_for_model_input.iloc[i].to_dict(),
                    "fraud_probability": fraud_probabilities[i],
                    "predicted_fraud_class": predicted_classes[i]
                })
        else: # If it doesn't have predict_proba, assume predict gives class directly
            predicted_classes = loaded_model.predict(data_for_model_input)
            for i in range(len(data_for_model_input)):
                 final_predictions.append({
                    "input_features": data_for_model_input.iloc[i].to_dict(),
                    "predicted_fraud_class": predicted_classes[i]
                })

        logger.info("Predictions made successfully.")

        # --- Display/Store Predictions ---
        print("\n--- Prediction Results ---")
        for i, pred_info in enumerate(final_predictions):
            original_event_id = identifiers.iloc[i]['event_id'] if identifiers is not None and 'event_id' in identifiers else f"record_{i}"
            print(f"Record ID: {original_event_id}")
            if "fraud_probability" in pred_info:
                print(f"  Predicted Fraud Probability: {pred_info['fraud_probability']:.4f}")
            print(f"  Predicted Fraud Class: {'FRAUD (1)' if pred_info['predicted_fraud_class'] == 1 else 'NOT FRAUD (0)'}")
            print("-" * 20)
        
    except Exception as e:
        logger.error(f"Error during prediction phase: {e}", exc_info=True)

    logger.info("Prediction process finished.")

if __name__ == "__main__":
    # Airflow can pass parameters as environment variables to BashOperator tasks
    # The DAG will set this environment variable based on its params.
    # Ensure the BashOperator's command in the DAG sets this.
    # Example DAG command:
    # bash_command="export MLFLOW_RUN_ID_FOR_PREDICTION={{ params.mlflow_run_id }} && python /opt/airflow/project_flows/predict.py"

    run_id_from_env = os.getenv("MLFLOW_RUN_ID_FOR_PREDICTION")
    
    if run_id_from_env:
        mlflow_run_id_to_use = run_id_from_env
        print(f"Using MLflow Run ID from environment variable: {mlflow_run_id_to_use}")
    else:
        # Fallback for direct testing - !!! REPLACE THIS FOR ACTUAL RUNS VIA AIRFLOW IF ENV VAR NOT SET !!!
        mlflow_run_id_to_use = "YOUR_MLFLOW_RUN_ID_HERE" 
        print(f"WARNING: MLFLOW_RUN_ID_FOR_PREDICTION env var not set. Using hardcoded fallback: {mlflow_run_id_to_use}")
        if mlflow_run_id_to_use == "YOUR_MLFLOW_RUN_ID_HERE":
            print("ERROR: Please set the MLFLOW_RUN_ID_FOR_PREDICTION environment variable or update the fallback Run ID in predict.py.")
            sys.exit(1) # Exit if no valid run ID is provided
            
    main_logger = setup_logger("predict_main_direct_run", level_str=config.LOG_LEVEL)
    main_logger.info(f"Prediction script executed for MLflow Run ID: {mlflow_run_id_to_use}")
    try:
        run_predictions(mlflow_run_id=mlflow_run_id_to_use)
    except Exception as e:
        main_logger.critical(f"Run of predict.py failed: {e}", exc_info=True)
        sys.exit(1) # Ensure Airflow task fails