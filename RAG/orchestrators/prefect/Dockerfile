FROM python:3.13-slim

WORKDIR /app

# Install uv — consistent with project toolchain
RUN pip install --no-cache-dir uv

# Install project dependencies from pyproject.toml.
# This installs all deps (FastAPI, OpenSearch, SQLAlchemy, Jina, etc.) that
# the nuke_ingestion task functions import transitively via api/.
COPY pyproject.toml uv.lock README.md /app/
COPY api/ /app/api/
RUN uv pip install --system .

# Install Prefect and remaining extras (ray, beautifulsoup4) — see requirements.txt
COPY orchestrators/prefect/requirements.txt /app/prefect-requirements.txt
RUN uv pip install --system -r prefect-requirements.txt

# Copy nuke ingestion task functions — imported directly by Prefect flows
COPY orchestrators/airflow/dags/nuke_ingestion/ /app/nuke_ingestion/

# Copy Prefect flows and deployment registration script
COPY orchestrators/prefect/flows/ /app/flows/
COPY orchestrators/prefect/deployments/ /app/deployments/

COPY orchestrators/prefect/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Makes api/ and nuke_ingestion/ importable without sys.path manipulation
ENV PYTHONPATH=/app

CMD ["/app/entrypoint.sh"]
