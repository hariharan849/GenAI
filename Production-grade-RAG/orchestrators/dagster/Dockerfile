FROM python:3.13-slim

WORKDIR /app

RUN pip install --no-cache-dir uv

# Install main project deps (api/ package needed by nuke_ingestion assets)
COPY pyproject.toml uv.lock README.md /app/
COPY api/ /app/api/
RUN uv pip install --system .

# Install Dagster and remaining extras (ray, beautifulsoup4) — see requirements.txt
COPY orchestrators/dagster/requirements.txt /app/dagster-requirements.txt
RUN uv pip install --system -r dagster-requirements.txt

# Copy nuke ingestion task functions reused by Dagster assets
COPY orchestrators/airflow/dags/nuke_ingestion/ /app/nuke_ingestion/

# Copy Dagster assets, definitions, and config
COPY orchestrators/dagster/assets/ /app/assets/
COPY orchestrators/dagster/definitions.py /app/definitions.py
COPY orchestrators/dagster/workspace.yaml /app/workspace.yaml
COPY orchestrators/dagster/dagster.yaml /app/dagster.yaml
COPY orchestrators/dagster/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Makes api/ and nuke_ingestion/ importable without sys.path manipulation
ENV PYTHONPATH=/app
# Tells Dagster where to find dagster.yaml
ENV DAGSTER_HOME=/app

ENTRYPOINT ["/app/entrypoint.sh"]
