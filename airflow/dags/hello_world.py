"""A minimal DAG used to verify the local Airflow scaffold."""

import logging
from datetime import datetime

from airflow.providers.standard.operators.python import PythonOperator

from airflow import DAG

logger = logging.getLogger(__name__)


def log_hello() -> None:
    """Write a hello message to the Airflow task log."""
    logger.info("Hello from the Yellow Cab Confessions scaffold.")


with DAG(
    dag_id="hello_world",
    description="Verify that the Airflow scheduler can parse and run a DAG.",
    start_date=datetime(2024, 1, 1),
    schedule=None,
    catchup=False,
    tags=["scaffold"],
) as dag:
    PythonOperator(
        task_id="say_hello",
        python_callable=log_hello,
    )
