# Monitoring Stack

Configuration files for the observability stack. All services are started as part of `docker compose up -d` (no extra profile needed).

---

## Components

| Service | Config file | Purpose |
|---------|-------------|---------|
| Prometheus | `prometheus/prometheus.yml` | Scrapes `/metrics` from the FastAPI container; stores time-series data |
| Grafana | `grafana/provisioning/` | Dashboards and datasource auto-provisioning |
| Loki | `loki/loki-config.yml` | Log aggregation — receives logs from Promtail |
| Promtail | `promtail/promtail-config.yml` | Tails Docker container logs and ships them to Loki |
| StatsD Exporter | `statsd_exporter/statsd_mapping.yml` | Converts StatsD metrics (from the API middleware) to Prometheus format |
| Node Exporter | Docker Compose service | Exposes host-level CPU, memory, disk, and network metrics |

---

## Grafana

- Available at `http://localhost:3000` (admin / admin)
- Datasources (Prometheus, Loki) are provisioned automatically from `grafana/provisioning/datasources/datasources.yml`
- Dashboards are provisioned from `grafana/provisioning/dashboards/dashboards.yml`
- Place custom dashboard JSON files in `grafana/dashboards/` to auto-load them on container start

---

## Prometheus

`prometheus/prometheus.yml` scrapes:
- `rag-api:8083/metrics` — FastAPI Prometheus metrics (`prometheus-fastapi-instrumentator` + custom singletons from `api/metrics.py`)
- `statsd-exporter:9102/metrics` — StatsD bridge metrics
- `node-exporter:9100/metrics` — host system metrics

Application request metrics exposed by the API include:
- `app_requests_total{service,method,endpoint,status}` — total HTTP requests
- `app_errors_total{service,type}` — warning (`4xx`) and critical (`5xx`) application errors
- `app_request_duration_seconds{service,method,endpoint,status}` — HTTP request latency histogram

---

## Loki + Promtail

Promtail watches the Docker socket and ships all container logs to Loki using labels derived from container metadata (`container_name`, `compose_service`). Query logs in Grafana Explore using LogQL.

---

## Alertmanager

The Slack webhook URL is injected at container start from `ALERTMANAGER_SLACK_WEBHOOK_URL` and written to a private file inside the Alertmanager container. Set the env var in your local `.env` or deployment secrets before starting the stack.

---

## StatsD

The FastAPI StatsD middleware (`api/middlewares.py`) emits per-route request counts and latencies. The exporter maps these to Prometheus metric names via `statsd_mapping.yml`.
