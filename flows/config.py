import os
from dotenv import load_dotenv

# Determine the directory of the current config.py file (which is 'flows/')
FLOWS_DIR_CONTEXT = os.path.dirname(os.path.abspath(__file__))

# Determine the project root directory (one level up from 'flows/')
PROJECT_ROOT_CONTEXT = os.path.abspath(os.path.join(FLOWS_DIR_CONTEXT, ".."))

# Load environment variables from .env file located in the 'flows' directory
dotenv_path = os.path.join(FLOWS_DIR_CONTEXT, '.env')
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path=dotenv_path)
else:
    print(f"WARNING: .env file not found at {dotenv_path}. Using default configurations.")

# --- General Configuration ---
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# --- Path Configuration ---
IS_IN_AIRFLOW_TASK = bool(os.getenv("AIRFLOW_CTX_DAG_ID"))

if IS_IN_AIRFLOW_TASK:
    # Inside Airflow task container, host's './data' is mounted at '/opt/airflow/project_data'
    BASE_DATA_DIR = "/opt/airflow/project_data"
    print(f"CONFIG.PY: Running in Airflow task context. Base data directory set to: {BASE_DATA_DIR}")
else:
    # Running locally (e.g., `python -m flows.generator` from project root)
    # The 'data' folder is at the project root level.
    BASE_DATA_DIR = os.path.join(PROJECT_ROOT_CONTEXT, "data")
    print(f"CONFIG.PY: Running in local context. Base data directory set to: {BASE_DATA_DIR}")

RAW_DATA_PATH = os.path.join(BASE_DATA_DIR, os.getenv("RAW_DIR_NAME", "raw"))
PRODUCER_RAW_DATA_PATH = RAW_DATA_PATH # Producer reads from the same raw data path
PROCESSED_RAW_DATA_PATH = os.path.join(BASE_DATA_DIR, os.getenv("PROCESSED_RAW_DIR_NAME", "processed_raw"))
SILVER_DATA_PATH = os.path.join(BASE_DATA_DIR, os.getenv("SILVER_DIR_NAME", "silver"))
GOLD_DATA_PATH = os.path.join(BASE_DATA_DIR, os.getenv("GOLD_DIR_NAME", "gold"))
MODELS_PATH = os.path.join(PROJECT_ROOT_CONTEXT, "models") # For models saved by train_model.py locally

# --- Data Generator Configuration ---
GENERATOR_SLEEP_MIN_SECONDS = int(os.getenv("GENERATOR_SLEEP_MIN_SECONDS", "5"))
GENERATOR_SLEEP_MAX_SECONDS = int(os.getenv("GENERATOR_SLEEP_MAX_SECONDS", "10"))

# --- Kafka Configuration ---
KAFKA_RAW_TOPIC = os.getenv("KAFKA_RAW_TOPIC", "claims_raw_topic")
PRODUCER_POLLING_INTERVAL_SECONDS = int(os.getenv("PRODUCER_POLLING_INTERVAL_SECONDS", "10"))

if IS_IN_AIRFLOW_TASK:
    KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS_DOCKER", "redpanda:29092")
else:
    KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS_LOCAL", "localhost:9092")
print(f"CONFIG.PY: Kafka Bootstrap Servers set to: {KAFKA_BOOTSTRAP_SERVERS}")


# --- Silver Processor Configuration ---
KAFKA_SILVER_CONSUMER_GROUP = os.getenv("KAFKA_SILVER_CONSUMER_GROUP", "silver-processor-group-airflow")
SILVER_BATCH_SIZE = int(os.getenv("SILVER_BATCH_SIZE", "100"))
SILVER_BATCH_TIMEOUT_SECONDS = int(os.getenv("SILVER_BATCH_TIMEOUT_SECONDS", "60"))

# --- Gold Processor Configuration ---
GOLD_PARQUET_FILENAME = os.getenv("GOLD_PARQUET_FILENAME", "claims_gold.parquet")
DUCKDB_FILENAME = os.getenv("DUCKDB_FILENAME", "claims_gold.duckdb")
DUCKDB_GOLD_TABLE_NAME = os.getenv("DUCKDB_GOLD_TABLE_NAME", "claims_gold_table")

# --- MLflow Configuration (for train_model.py) ---
MLFLOW_EXPERIMENT_NAME = os.getenv("MLFLOW_EXPERIMENT_NAME", "openclaims_fraud_detection")
if IS_IN_AIRFLOW_TASK:
    MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI_DOCKER", "http://mlflow:5000")
else:
    # For local runs, construct path to mlruns at project root
    local_mlruns_path = os.path.join(PROJECT_ROOT_CONTEXT, os.getenv("MLFLOW_TRACKING_URI_LOCAL_FILE_BASE", "mlruns"))
    MLFLOW_TRACKING_URI = "file:" + local_mlruns_path

print(f"CONFIG.PY: MLflow Tracking URI set to: {MLFLOW_TRACKING_URI}")
print(f"CONFIG.PY: MLflow Experiment Name set to: {MLFLOW_EXPERIMENT_NAME}")

# Print all resolved data paths for verification when config.py is imported
# This is for debugging during development. Can be commented out in production.
# print(f"CONFIG.PY Resolved Data Paths:")
# print(f"  Raw Data Path: {RAW_DATA_PATH}")
# print(f"  Producer Raw Data Path: {PRODUCER_RAW_DATA_PATH}")
# print(f"  Processed Raw Data Path: {PROCESSED_RAW_DATA_PATH}")
# print(f"  Silver Data Path: {SILVER_DATA_PATH}")
# print(f"  Gold Data Path: {GOLD_DATA_PATH}")
# print(f"  Models Path (local): {MODELS_PATH}")