# Orchestrators — Ingestion Pipelines

Three interchangeable orchestration frameworks for the Nuke documentation ingestion pipeline. All three implement the same logical steps; choose one to run alongside shared infrastructure.

---

## Pipeline Steps

```
scrape_nuke_docs
      │  (crawl Foundry Nuke 17.0 reference guide, extract node pages)
      ▼
save_nuke_pages_to_db
      │  (upsert scraped pages into PostgreSQL nuke_pages table)
      ▼
index_nuke_docs
      │  (chunk → embed with Jina AI v3 → bulk index into OpenSearch)
      ▼
generate_nuke_report
      │  (summary of ingestion statistics)
      ▼
cleanup_temp_files
```

---

## Comparison

| Feature | Airflow | Prefect | Dagster |
|---------|---------|---------|---------|
| UI port | 8081 | 4200 | 3002 |
| Docker profile | `airflow` | `prefect` | `dagster` |
| Paradigm | DAG tasks | Python flows | Software-defined assets |
| Executor | CeleryExecutor | Worker process | gRPC user-code server |
| Trigger | Manual (UI or CLI) | UI / API / CLI | UI / CLI |
| Containers added | 5 (webserver, scheduler, worker, flower, init) | 2 (server, worker) | 3 (grpc, webserver, daemon) |

---

## Starting an Orchestrator

Run from the repo root:

```bash
# Airflow
docker compose --profile airflow up -d

# Prefect
docker compose --profile prefect up -d

# Dagster
docker compose --profile dagster up -d
```

Only one orchestrator needs to run at a time. Bare `docker compose up -d` starts shared infrastructure only.

---

## Subdirectory READMEs

- [`airflow/README.md`](airflow/README.md)
- [`prefect/README.md`](prefect/README.md)
- [`dagster/README.md`](dagster/README.md)
