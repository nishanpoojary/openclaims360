# OpenClaims 360: End-to-End Fraud Detection Platform

This project demonstrates a complete, containerized data platform designed to ingest, process, and analyze insurance claims data to identify potential fraud. It integrates modern data engineering and MLOps principles, from real-time data streaming to orchestrated model training and experiment tracking.

## Tech Stack

* **Orchestration:** Apache Airflow
* **Data Streaming:** Apache Kafka (Redpanda)
* **ML Lifecycle & Experiment Tracking:** MLflow
* **Data Processing & Storage:** Python, Pandas, DuckDB, Parquet
* **Infrastructure & Containerization:** Docker, Docker Compose

## Project Architecture

1.  **Data Ingestion:** A Python script generates synthetic claim events and produces them to a Kafka (Redpanda) topic.
2.  **ETL Pipeline (Orchestrated by Airflow):**
    * **Silver Layer:** A batch task consumes raw data from Kafka, performs initial cleaning and type casting, and saves it as partitioned Parquet files.
    * **Gold Layer:** A subsequent task reads the Silver data, performs feature engineering, and creates an analytics-ready Gold layer in both Parquet format and a DuckDB database.
3.  **Model Training & MLOps:**
    * An Airflow task triggers a Python script to train a `LightGBM` classification model on the Gold data.
    * **MLflow** is used to log all experiment details: parameters, performance metrics (AUC, Precision, Recall), and the trained model itself as an artifact.
4.  **Prediction Pipeline:**
    * A separate Airflow DAG loads a trained model from the MLflow Model Registry and runs predictions on new data.

## How to Run

1.  **Prerequisites:** Docker and Docker Compose must be installed.

2.  **Clone the Repository:**
    ```bash
    git clone [https://github.com/nishanpoojary/openclaims360.git](https://github.com/nishanpoojary/openclaims360.git)
    cd openclaims360
    ```

3.  **Create Local Directories:**
    The Airflow setup requires these empty directories to exist before starting:
    ```bash
    mkdir -p dags logs plugins data mlruns models superset_home
    ```

4.  **Build and Start Services:**
    This will build the custom Airflow image and start all services (Airflow, Redpanda, MLflow, Postgres).
    ```bash
    docker-compose up -d --build
    ```
    On the first run, the `airflow-init` service will set up the database and create a default user (`admin`/`admin`). This may take a few minutes.

5.  **Access Services:**
    * **Airflow UI:** `http://localhost:8080` (Login: `admin` / `admin`)
    * **MLflow UI:** `http://localhost:5000`

6.  **Run the Pipeline:**
    * Unpause the `openclaims_data_pipeline_v1` and `openclaims_prediction_pipeline_v1` DAGs in the Airflow UI.
    * Start the data generator and producer scripts in separate terminals to feed data into Kafka:
        ```bash
        # Terminal 1 (from project root)
        # You may need to create and activate a Python virtual environment first
        # python -m venv flows/.venv && source flows/.venv/bin/activate (Linux/macOS)
        # pip install -r flows/requirements.txt
        python -m flows.generator
        ```
        ```bash
        # Terminal 2 (from project root, venv activated)
        python -m flows.producer
        ```
    * Manually trigger the `openclaims_data_pipeline_v1` DAG in the Airflow UI to run the data processing and model training pipeline.
    * After a model is trained and registered in MLflow, trigger the `openclaims_prediction_pipeline_v1` DAG to run predictions.