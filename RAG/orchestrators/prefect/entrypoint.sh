#!/bin/bash
set -e

# Create work pool — idempotent, safe on every startup (exits 0 if already exists)
prefect work-pool create local-process-pool --type process 2>/dev/null || true

# Register the deployment (idempotent — updates schedule if already registered)
python /app/deployments/nuke_ingestion_deployment.py

# Start the process worker — runs flows as subprocess forks within this container
exec prefect worker start --pool local-process-pool --type process
