ARG AIRFLOW_VERSION=3.3.2
ARG PYTHON_VERSION=3.14
FROM apache/airflow:${AIRFLOW_VERSION}-python${PYTHON_VERSION}

ARG AIRFLOW_VERSION
ARG PYTHON_VERSION
ARG DBT_CORE_VERSION=1.12.6
ARG DBT_DUCKDB_VERSION=1.11.1
ARG DUCKDB_VERSION=2.0.0

USER root
RUN mkdir -p /opt/airflow/yellow-cab-confessions \
    && chown airflow:root /opt/airflow/yellow-cab-confessions

USER airflow
WORKDIR /opt/airflow/yellow-cab-confessions

USER root
COPY airflow/entrypoint.sh /usr/local/bin/ycc-airflow-entrypoint
RUN chmod 755 /usr/local/bin/ycc-airflow-entrypoint

USER airflow
RUN python -m venv /home/airflow/dbt-venv \
    && /home/airflow/dbt-venv/bin/pip install --no-cache-dir \
        "dbt-core==${DBT_CORE_VERSION}" \
        "dbt-duckdb==${DBT_DUCKDB_VERSION}" \
        "duckdb==${DUCKDB_VERSION}" \
    && /home/airflow/dbt-venv/bin/pip check
ENV PATH="/home/airflow/dbt-venv/bin:${PATH}"

COPY --chown=airflow:root pyproject.toml LICENSE ./
COPY --chown=airflow:root ycc ./ycc
RUN /usr/local/bin/python -m pip install --no-cache-dir --no-deps .

WORKDIR /opt/airflow
ENTRYPOINT ["/usr/bin/dumb-init", "--", "/usr/local/bin/ycc-airflow-entrypoint"]
