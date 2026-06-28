# Airflow Orchestrator

CeleryExecutor-based Airflow setup for the Nuke documentation ingestion pipeline.

---

## Starting

```bash
# From repo root
docker compose --profile airflow up -d
```

UI is available at `http://localhost:8081` (default credentials: `admin` / `admin`).

---

## DAG

**`nuke_docs_ingestion`** — manually triggered, no schedule.

Task order:

```
setup → scrape_nuke_docs → save_nuke_pages_to_db → index_nuke_docs → generate_nuke_report → cleanup_temp_files
```

Trigger the DAG from the Airflow UI or via:

```bash
docker exec airflow-webserver airflow dags trigger nuke_docs_ingestion
```

---

## Directory Structure

```
airflow/
├── dags/
│   └── nuke_ingestion/
│       ├── dag.py          # DAG definition and task wiring
│       ├── scraping.py     # Crawls Nuke 17.0 reference guide, writes JSON via XCom
│       ├── save.py         # Upserts pages to PostgreSQL via NukePageRepository
│       └── indexing.py     # Chunks, embeds, and bulk-indexes into OpenSearch
├── config/                 # airflow.cfg overrides
├── plugins/                # Custom Airflow plugins (if any)
├── logs/                   # Task execution logs (gitignored)
├── Dockerfile              # Airflow image with project dependencies
└── requirements-airflow.txt
```

---

## Containers

| Container | Role |
|-----------|------|
| `airflow-webserver` | Web UI |
| `airflow-scheduler` | DAG scheduling |
| `airflow-worker` | Task execution (Celery) |
| `airflow-flower` | Celery worker monitoring |
| `airflow-init` | DB migrations + admin user creation (runs once) |

---

## Environment Variables

The Airflow containers inherit the root `.env`. Key variables used by ingestion tasks:

- `POSTGRES_*` — PostgreSQL connection for NukePageRepository
- `OPENSEARCH__*` — OpenSearch connection for indexing
- `JINA_API_KEY` — Jina AI embeddings
