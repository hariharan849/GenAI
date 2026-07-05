# Prefect Orchestrator

Prefect-based ingestion pipeline for Nuke documentation. Mirrors the Airflow DAG as a Prefect flow with a worker deployment.

---

## Starting

```bash
# From repo root
docker compose --profile prefect up -d
# Or equivalently:
COMPOSE_PROFILES=prefect docker compose up -d
```

UI is available at `http://localhost:4200`.

---

## Directory Structure

```
prefect/
├── flows/
│   └── nuke_docs_ingestion.py    # Prefect flow definition (all pipeline steps)
├── deployments/
│   └── nuke_ingestion_deployment.py  # Deployment config (work pool, schedule)
├── Dockerfile                    # Prefect worker image
└── entrypoint.sh                 # Worker startup script
```

---

## Running a Flow

Trigger from the Prefect UI at `http://localhost:4200`, or via CLI:

```bash
docker exec prefect-worker prefect deployment run 'nuke-docs-ingestion/default'
```

---

## Building the Worker Image

```bash
docker compose build prefect-worker
```

---

## Containers

| Container | Role |
|-----------|------|
| `prefect-server` | Prefect API + UI |
| `prefect-worker` | Executes flow runs |

---

## Environment Variables

Prefect worker inherits the root `.env`. Key variables:

- `PREFECT_API_URL` — points the worker at the local Prefect server
- `POSTGRES_*`, `OPENSEARCH__*`, `JINA_API_KEY` — used by flow tasks
