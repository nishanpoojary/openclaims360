# openclaims_fresh_start/dags/prediction_pipeline_dag.py
from __future__ import annotations
import pendulum
from airflow.models.dag import DAG
from airflow.operators.bash import BashOperator
from airflow.models.param import Param

PROJECT_FLOWS_DIR_IN_CONTAINER = "/opt/airflow/project_flows"

with DAG(
    dag_id="openclaims_prediction_pipeline_v1",
    start_date=pendulum.datetime(2024, 1, 1, tz="UTC"),
    catchup=False,
    schedule=None,
    tags=["openclaims", "prediction"],
    doc_md="DAG to run fraud predictions using a trained model.",
    params={
        "mlflow_run_id": Param(
            "39b98dab15234790b3050b39d0861471", 
            type="string",
            title="MLflow Run ID",
            description="The MLflow Run ID of the trained model to use for prediction.",
        )
    }
) as dag:

    run_prediction_task = BashOperator(
        task_id="run_fraud_predictions",
        bash_command="python /opt/airflow/project_flows/predict.py",
        env={
            "MLFLOW_RUN_ID_FOR_PREDICTION": "{{ params.mlflow_run_id }}" 
        },
        doc_md="Runs the fraud prediction script."
    )