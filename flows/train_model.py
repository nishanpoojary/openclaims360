import os
import sys
import config 
from common.logging_utils import setup_logger
import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from lightgbm import LGBMClassifier
from sklearn.metrics import accuracy_score, precision_score, recall_score, roc_auc_score
import joblib
import mlflow

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

# module_logger = setup_logger(__name__, level_str=config.LOG_LEVEL) # Optional module-level logger

# Paths (config.py resolves GOLD_DATA_PATH to absolute)
GOLD_PARQUET_FULL_PATH = os.path.join(config.GOLD_DATA_PATH, config.GOLD_PARQUET_FILENAME)

# Model save path (this will be inside the Airflow worker container when run by Airflow)
# MLflow is the primary model storage. This local pickle is for convenience/backup during task execution.
# config.MODELS_PATH is defined in config.py relative to project root, for local saves.
# When run in Airflow, this will be relative to where the task executes, e.g., /opt/airflow/project_flows/models
# This path needs to be accessible for writing by the Airflow task.
# We will use config.MODELS_PATH which resolves to host's ./models when running locally,
# and /opt/airflow/project_data/models (if we choose to map ./models to project_data/models) or
# /opt/airflow/project_flows/models (if scripts are expected to write within their own dir structure).

MODEL_DIR_IN_TASK = os.path.join(config.PROJECT_ROOT_CONTEXT, "models_task_output") # Path on the host system
MODEL_FILENAME = "fraud_model_airflow_task.pkl"
MODEL_PATH_IN_TASK = os.path.join(MODEL_DIR_IN_TASK, MODEL_FILENAME)


def setup_mlflow_for_run(logger_instance):
    """Sets MLflow tracking URI and experiment."""
    try:
        # Use URI from config (which is context-aware: http://mlflow:5000 for Docker, file: for local)
        mlflow.set_tracking_uri(config.MLFLOW_TRACKING_URI)
        experiment = mlflow.get_experiment_by_name(config.MLFLOW_EXPERIMENT_NAME)
        if experiment is None:
            logger_instance.info(f"MLflow experiment '{config.MLFLOW_EXPERIMENT_NAME}' not found, creating it...")
            mlflow.create_experiment(config.MLFLOW_EXPERIMENT_NAME)
            # Re-fetch after creation to ensure we have the experiment object
            mlflow.set_experiment(config.MLFLOW_EXPERIMENT_NAME) 
        else:
            mlflow.set_experiment(config.MLFLOW_EXPERIMENT_NAME)
            
        logger_instance.info(f"MLflow tracking URI successfully set to: {config.MLFLOW_TRACKING_URI}")
        logger_instance.info(f"MLflow experiment successfully set to: {config.MLFLOW_EXPERIMENT_NAME}")
    except Exception as e:
        logger_instance.error(f"Error setting up MLflow (URI: {config.MLFLOW_TRACKING_URI}, Exp: {config.MLFLOW_EXPERIMENT_NAME}): {e}", exc_info=True)
        raise # Fail task if MLflow setup fails

def load_gold_data_for_training(logger_instance) -> pd.DataFrame:
    logger_instance.info(f"Loading Gold data from {GOLD_PARQUET_FULL_PATH} …")
    try:
        df = pd.read_parquet(GOLD_PARQUET_FULL_PATH)
        logger_instance.info(f"Loaded {df.shape[0]} rows, {df.shape[1]} columns from Gold.")
        if df.empty:
            logger_instance.warning("Gold data is empty. Training cannot proceed effectively.")
        return df
    except FileNotFoundError:
        logger_instance.error(f"ERROR: Gold Parquet file not found at {GOLD_PARQUET_FULL_PATH}")
        raise 
    except Exception as e:
        logger_instance.error(f"ERROR: Could not load Gold Parquet file {GOLD_PARQUET_FULL_PATH}: {e}", exc_info=True)
        raise

def prepare_data_for_model(df: pd.DataFrame, logger_instance) -> tuple[pd.DataFrame, pd.Series, list]:
    if df.empty:
        logger_instance.warning("Input DataFrame is empty for data preparation.")
        return pd.DataFrame(), pd.Series(dtype='int'), []

    df_processed = df.copy()
    if "FraudFound_P" not in df_processed.columns:
        logger_instance.error("Target column 'FraudFound_P' is MISSING from Gold data!")
        raise ValueError("Target column 'FraudFound_P' not found in input DataFrame for training.")
    else:
        logger_instance.info("Using 'FraudFound_P' column from Gold data as target.")

    if df_processed["FraudFound_P"].isnull().any():
        logger_instance.warning(f"Target column 'FraudFound_P' contains NaN values. Filling with 0.")
        df_processed["FraudFound_P"].fillna(0, inplace=True) 
    df_processed.replace([np.inf, -np.inf], np.nan, inplace=True) 
    if df_processed["FraudFound_P"].isnull().any():
        logger_instance.warning(f"Target column 'FraudFound_P' still contains NaN after inf conversion. Filling with 0.")
        df_processed["FraudFound_P"].fillna(0, inplace=True)
    
    y = df_processed["FraudFound_P"].astype(int)

    feature_cols = [
        'amount', 'days_since_policy_start', 'loss_type_cat',
        'amount_per_day_on_policy', 'is_very_new_policy',
        'high_amount_on_new_policy', 'event_month',
        'event_day_of_week', 'event_hour'
    ]
    
    actual_feature_cols = [col for col in feature_cols if col in df_processed.columns]
    if not actual_feature_cols:
        logger_instance.error("No feature columns available for training after filtering. Check Gold data and feature_cols definition.")
        return pd.DataFrame(), y, [] # Return empty X but potentially valid y and empty features list
    
    X = df_processed[actual_feature_cols].copy()
    logger_instance.info(f"Initial X created with columns: {X.columns.tolist()}")

    if X.empty:
        logger_instance.warning("Feature DataFrame X is empty before NaN handling. Returning empty X.")
        return X, y, actual_feature_cols

    for col in X.columns:
        if X[col].isnull().any():
            fill_value = X[col].median() if pd.api.types.is_numeric_dtype(X[col]) else X[col].mode()[0] if not X[col].mode().empty else 0
            X[col].fillna(fill_value, inplace=True)
            logger_instance.info(f"Filled NaN in feature '{col}' with '{fill_value}'.")
    
    logger_instance.info(f"Prepared features: {actual_feature_cols}. X shape: {X.shape}, y shape: {y.shape}")
    return X, y, actual_feature_cols

def split_data(X: pd.DataFrame, y: pd.Series, logger_instance) -> tuple:
    if X.empty or y.empty:
        logger_instance.warning("Features (X) or target (y) is empty. Cannot split data.")
        return pd.DataFrame(columns=X.columns), pd.DataFrame(columns=X.columns), pd.Series(dtype=y.dtype), pd.Series(dtype=y.dtype)
    
    stratify_option = y if y.nunique() > 1 and all(y.value_counts() >= 2) else None # Check for min samples per class for stratify
    if stratify_option is None and y.nunique() > 1:
        logger_instance.warning("Not enough samples in at least one class for stratification, proceeding without it.")

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=stratify_option
    )
    logger_instance.info(f"Data split: Train rows = {len(X_train)}, Test rows = {len(X_test)}")
    return X_train, X_test, y_train, y_test

def train_log_evaluate_model(X_train, y_train, X_test, y_test, feature_cols, logger_instance):
    if X_train.empty or y_train.empty:
        logger_instance.error("Training data (X_train or y_train) is empty. Skipping model training.")
        return None

    # This directory is inside the Airflow worker container.
    os.makedirs(MODEL_DIR_IN_TASK, exist_ok=True) 

    try:
        with mlflow.start_run(nested=True) as run: 
            run_id = run.info.run_id
            logger_instance.info(f"Starting MLflow Run ID: {run_id} for model training.")
            mlflow.log_params({"features": feature_cols, "model_type": "LGBMClassifier", 
                               "training_rows": len(X_train), "test_rows": len(X_test)})

            model = LGBMClassifier(objective="binary", random_state=42)
            try:
                model.fit(X_train, y_train, eval_set=[(X_test, y_test)], eval_metric="auc")
            except Exception as e:
                logger_instance.error(f"Error during model.fit: {e}", exc_info=True)
                mlflow.set_tag("training_status", "failed_fit")
                mlflow.log_param("training_error", str(e))
                raise 

            if not X_test.empty and not y_test.empty:
                y_pred_proba = model.predict_proba(X_test)[:, 1]
                y_pred = model.predict(X_test)
                acc = accuracy_score(y_test, y_pred)
                prec = precision_score(y_test, y_pred, zero_division=0)
                rec = recall_score(y_test, y_pred, zero_division=0)
                auc_score_val = roc_auc_score(y_test, y_pred_proba) if y_test.nunique() > 1 and len(y_test) > 0 else 0.5 
                
                logger_instance.info(f"Test Metrics: Acc={acc:.3f}, Prec={prec:.3f}, Rec={rec:.3f}, AUC={auc_score_val:.3f}")
                mlflow.log_metric("accuracy", acc); mlflow.log_metric("precision", prec)
                mlflow.log_metric("recall", rec); mlflow.log_metric("auc", auc_score_val)
                mlflow.set_tag("training_status", "success")
            else:
                logger_instance.warning("Test set is empty. Skipping metric calculation and logging to MLflow.")
                mlflow.set_tag("training_status", "completed_no_test_metrics")

            try:
                mlflow.sklearn.log_model(sk_model=model, artifact_path="lgbm_fraud_model")
                logger_instance.info("Model logged to MLflow artifact store.")
            except Exception as e:
                logger_instance.error(f"Error logging model to MLflow: {e}", exc_info=True)
            
            try:
                # This saves the model inside the Airflow worker container at MODEL_PATH_IN_TASK
                # This path is not automatically persisted on the host unless MODEL_DIR_IN_TASK is part of a mount.
                # The primary model artifact is the one logged to MLflow.
                joblib.dump(model, MODEL_PATH_IN_TASK) 
                logger_instance.info(f"Saved model temporarily to {MODEL_PATH_IN_TASK} (within task container)")
            except Exception as e:
                logger_instance.error(f"Error saving model locally with joblib: {e}", exc_info=True)
            
            logger_instance.info(f"MLflow run {run_id} complete for this training task.")
            return run_id
    except Exception as e:
        logger_instance.error(f"Failed to start or complete MLflow run: {e}", exc_info=True)
        raise 

def run_model_training_pipeline():
    """Main function to orchestrate model training."""
    logger = setup_logger(f"{__name__}.run_model_training_pipeline", level_str=config.LOG_LEVEL)
    logger.info("Starting Model Training Pipeline...")

    try:
        setup_mlflow_for_run(logger)
    except Exception as e:
        logger.error(f"Halting pipeline due to MLflow setup failure: {e}")
        raise # Fail the Airflow task if MLflow can't be set up

    df_gold = load_gold_data_for_training(logger)
    if df_gold.empty:
        logger.warning("Gold data is empty. Terminating training pipeline.")
        return # For Airflow, if this is an error, raise an exception. For now, just return.

    X, y, features = prepare_data_for_model(df_gold, logger)
    if X.empty or not features: # Check if X is empty OR if features list is empty
        logger.warning("No features to train on after preparation or X is empty. Terminating training pipeline.")
        return # Or raise error to fail Airflow task

    X_train, X_test, y_train, y_test = split_data(X, y, logger)
    if X_train.empty or y_train.empty:
        logger.warning("Training data (X_train or y_train) is empty after split. Terminating training pipeline.")
        return

    run_id = train_log_evaluate_model(X_train, y_train, X_test, y_test, features, logger)
    if run_id:
        logger.info(f"Model Training Pipeline finished successfully. MLflow Run ID: {run_id}")
    else:
        logger.warning("Model Training Pipeline finished, but model training task did not return a run ID or failed.")

if __name__ == "__main__":
    # This makes the script callable for Airflow's BashOperator
    run_model_training_pipeline()