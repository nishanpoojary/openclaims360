# openclaims_fresh_start/dags/openclaims_pipeline_dag.py
from __future__ import annotations
import pendulum
from airflow.models.dag import DAG
from airflow.operators.bash import BashOperator

with DAG(
    dag_id="openclaims_data_pipeline_v1", 
    start_date=pendulum.datetime(2024, 1, 1, tz="UTC"),
    catchup=False,
    schedule="@daily",
    tags=["openclaims"],
    doc_md="DAG to process OpenClaims data: Silver -> Gold -> Train Model."
) as dag:

    run_silver_processing = BashOperator(
        task_id="run_silver_processor_batch",
        bash_command="python /opt/airflow/project_flows/silver_processor.py",
        doc_md="Runs the Silver layer processing script as a batch."
    )

    run_gold_processor = BashOperator(
        task_id="run_gold_processor",
        bash_command="python /opt/airflow/project_flows/gold_processor.py",
        doc_md="Runs the Gold layer processing script."
    )

    run_train_model = BashOperator(
        task_id="run_train_model",
        bash_command="python /opt/airflow/project_flows/train_model.py",
        doc_md="Runs the model training script."
    )

    # Define dependencies
    run_silver_processing >> run_gold_processor >> run_train_model