FROM apache/airflow:3.2.1

USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

USER airflow

RUN pip install --no-cache-dir \
    opensearch-py>=3.0.0 \
    psycopg2-binary>=2.9.10 \
    sqlalchemy>=2.0.0 \
    pydantic>=2.11.3 \
    pydantic-settings>=2.8.1 \
    requests>=2.32.3 \
    httpx>=0.28.1 \
    langfuse>=3.0.0 \
    redis>=6.4.0 \
    datasketch>=1.6.0 \
    "ray[data]>=2.10" \
    sentence-transformers>=3.0.0 \
    instructor>=1.0 \
    openai>=1.0
