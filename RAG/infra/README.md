# Infrastructure

Infrastructure configuration for local development (Docker Compose + monitoring stack) and AWS production deployment (Terraform 4-layer).

---

## Directory Structure

```
infra/
├── monitoring/        # Observability stack configuration files
│   ├── grafana/       # Dashboard provisioning + datasource definitions
│   ├── loki/          # Log aggregation config
│   ├── prometheus/    # Metrics scrape config
│   ├── promtail/      # Log forwarding agent config
│   └── statsd_exporter/ # StatsD → Prometheus bridge mapping
├── nginx/
│   └── nginx.conf     # Reverse proxy: routes / to UI, /api/ to FastAPI
└── terraform/         # AWS infrastructure-as-code (see terraform/README.md)
    ├── bootstrap/     # S3 state bucket + DynamoDB lock table
    ├── layers/        # 4 independently deployable layers
    │   ├── 01-infra/  # VPC, OpenSearch EC2, Postgres, Redis, Langfuse, monitoring
    │   ├── 02-api/    # FastAPI + Ollama EC2
    │   ├── 03-ui/     # Next.js UI EC2
    │   └── 04-endpoints/ # ALB + target groups + DNS
    └── modules/       # Reusable Terraform modules (ec2, iam, networking, security)
```

---

## Local Monitoring Stack

Started automatically with `docker compose up -d`. Access points:

| Service | URL | Credentials |
|---------|-----|-------------|
| Grafana | http://localhost:3000 | admin / admin |
| Prometheus | http://localhost:9099 | — |
| Loki | http://localhost:3100 | — |
| OpenSearch Dashboards | http://localhost:5601 | — |
| Langfuse | http://localhost:3001 | see `.env` |

Grafana dashboards are provisioned automatically from `infra/monitoring/grafana/provisioning/`. The Prometheus scrape config in `infra/monitoring/prometheus/prometheus.yml` points to `rag-api:8083/metrics`.

Promtail ships container logs from Docker socket to Loki. The StatsD exporter converts StatsD metrics from the API middleware into Prometheus format.

---

## Redis Cache Modes

Plain Redis supports the existing exact-match cache for `/ask` and `/stream`.
Semantic final-answer caching is disabled by default and requires Redis Stack
or another Redis deployment with RediSearch vector commands. The API checks
`FT._LIST` at startup; if unsupported, semantic cache is bypassed and the app
continues serving live RAG.

For AWS, do not enable `REDIS__SEMANTIC_CACHE_ENABLED=true` unless the Redis
layer exposes RediSearch/vector search. When rolling out a new ingestion,
prompt, search backend, or chunking configuration, rotate
`REDIS__SEMANTIC_CACHE_SCOPE_VERSION` or drop the semantic cache index.

---

## Nginx

`infra/nginx/nginx.conf` configures:

- `GET /` and all non-API paths → forward to Next.js UI (`:3004`)
- `GET /api/*` → forward to FastAPI (`:8083`)

This lets the browser use a single origin (`http://localhost:80`) for both UI and API.

---

## AWS Deployment

See [`terraform/README.md`](terraform/README.md) for full deployment instructions.

High-level layout:
- **Layer 01** — shared infrastructure EC2 (OpenSearch, PostgreSQL, Redis, Langfuse, monitoring)
- **Layer 02** — API EC2 (FastAPI + Ollama)
- **Layer 03** — UI EC2 (Next.js)
- **Layer 04** — Application Load Balancer + target groups

Estimated monthly cost: ~$228 on-demand / ~$95 with 1-year Reserved Instances.
