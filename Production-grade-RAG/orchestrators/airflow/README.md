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

**`nuke_kg_extraction`** — manually triggered KG-only backfill. It does not
scrape or index docs; it reads indexed PostgreSQL pages where `kg_extracted` is
false and writes triples to Neo4j.

Run pending KG extraction only:

```bash
docker exec airflow-webserver airflow dags trigger nuke_kg_extraction
```

Reset indexed pages to pending KG first, then extract:

```bash
docker exec airflow-webserver airflow dags trigger nuke_kg_extraction --conf '{"reset_kg_extracted": true}'
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
