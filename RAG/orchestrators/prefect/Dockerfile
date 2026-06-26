FROM python:3.13-slim

WORKDIR /app

# Install uv — consistent with project toolchain
RUN pip install --no-cache-dir uv

# Install project dependencies from pyproject.toml.
# This installs all deps (FastAPI, OpenSearch, SQLAlchemy, Jina, etc.) that
# the arxiv_ingestion task functions import transitively via src/.
COPY pyproject.toml uv.lock /app/
COPY src/ /app/src/
RUN uv pip install --system .

# Install Prefect separately — see requirements.txt for pinning instructions
COPY prefect/requirements.txt /app/prefect-requirements.txt
RUN uv pip install --system -r prefect-requirements.txt

# Copy DAG task functions — imported directly by Prefect flows
COPY airflow/dags/arxiv_ingestion/ /app/arxiv_ingestion/

# Copy Prefect flows and deployment registration script
COPY prefect/flows/ /app/flows/
COPY prefect/deployments/ /app/deployments/

COPY prefect/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Makes both `src` and `arxiv_ingestion` importable without sys.path manipulation
ENV PYTHONPATH=/app

CMD ["/app/entrypoint.sh"]
