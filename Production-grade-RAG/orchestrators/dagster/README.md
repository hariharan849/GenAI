# Dagster Orchestrator

Software-defined asset pipeline for Nuke documentation ingestion. Assets remain available for lineage tracking, and the main `nuke_docs_ingestion` job uses dynamic indexing batch ops for visible fan-out.

---

## Starting

```bash
# From repo root
docker compose --profile dagster up -d
# Or build first if the image changed:
docker compose --profile dagster build
```

UI (asset lineage graph) is available at `http://localhost:3002`.

---

## Directory Structure

```
dagster/
├── assets/
│   └── nuke_ingestion.py     # All four assets: scraped, saved, indexed, report
├── definitions.py             # Wires assets into nuke_docs_ingestion job
├── dagster.yaml               # Dagster instance configuration
├── workspace.yaml             # Tells Dagster where to find user code
├── Dockerfile                 # Shared image for all three Dagster containers
└── entrypoint.sh              # Per-container startup logic
```

---

## Assets

| Asset | Description |
|-------|-------------|
| `scraped_nuke_pages` | Crawls Nuke 17.0 reference guide and returns raw page data |
| `saved_nuke_pages` | Upserts scraped pages into PostgreSQL |
| `indexed_nuke_docs` | Prepares batches, chunks, embeds (Jina), and indexes into OpenSearch |
| `nuke_ingestion_report` | Summary statistics for the ingestion run |

All assets are grouped under the `nuke_ingestion` asset group. The `nuke_docs_ingestion` job in `definitions.py` runs the same pipeline with dynamic `index_nuke_docs_batch[batch_N]` ops and an `index_finalize` reducer.

---

## Running the Dynamic Job

From the Dagster UI at `http://localhost:3002`, launch the `nuke_docs_ingestion` job to see batch indexing fan out as dynamic mapped ops.

---

## Materializing Assets

From the Dagster UI at `http://localhost:3002`:

1. Navigate to **Assets** → select all assets in the `nuke_ingestion` group
2. Click **Materialize selected**

Or via CLI:

```bash
docker exec dagster-webserver dagster asset materialize --select "nuke_ingestion/*"
```

---

## Containers

All three containers share a single Docker image built from `Dockerfile`. `entrypoint.sh` selects the role based on the `DAGSTER_ROLE` environment variable.

| Container | Role |
|-----------|------|
| `dagster-grpc` | User-code gRPC server (loads asset definitions) |
| `dagster-webserver` | Web UI + GraphQL API |
| `dagster-daemon` | Background scheduler and sensor daemon |

---

## Environment Variables

- `DAGSTER_HOME` — path to Dagster instance storage (set in `dagster.yaml`)
- `POSTGRES_*`, `OPENSEARCH__*`, `JINA_API_KEY` — used by asset materializations
