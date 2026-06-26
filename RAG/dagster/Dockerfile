FROM python:3.13-slim

WORKDIR /app

RUN pip install --no-cache-dir uv

# Install main project deps (src/ imports transitively needed by arxiv_ingestion/)
COPY pyproject.toml uv.lock README.md /app/
COPY src/ /app/src/
RUN uv pip install --system .

# Install Dagster packages
COPY dagster/requirements.txt /app/dagster-requirements.txt
RUN uv pip install --system -r dagster-requirements.txt

# Copy task functions reused by assets (same directory the Prefect Dockerfile copies)
COPY airflow/dags/arxiv_ingestion/ /app/arxiv_ingestion/

# Copy Dagster assets, definitions, and config
COPY dagster/assets/ /app/assets/
COPY dagster/definitions.py /app/definitions.py
COPY dagster/workspace.yaml /app/workspace.yaml
COPY dagster/dagster.yaml /app/dagster.yaml
COPY dagster/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Makes both `src` and `arxiv_ingestion` importable without sys.path manipulation
ENV PYTHONPATH=/app
# Tells Dagster where to find dagster.yaml
ENV DAGSTER_HOME=/app

ENTRYPOINT ["/app/entrypoint.sh"]
