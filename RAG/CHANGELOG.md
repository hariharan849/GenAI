# Changelog

All notable changes to the Nuke RAG system.

## [Unreleased] - 2026-06-28

### Added
- **Terraform 4-layer AWS infrastructure** (`infra/terraform/`): independently deployable layers
  for infra (OpenSearch, PostgreSQL, Redis, Langfuse, observability), api (FastAPI + Ollama),
  ui (Next.js), and endpoints (ALB with path-based routing). State stored in S3 with DynamoDB locking.
- Docker Compose split: `docker-compose.infra.yaml`, `docker-compose.api.yaml`,
  `docker-compose.ui.yaml` for layered AWS deployment.
- Terraform bootstrap module for S3 state bucket and DynamoDB lock table.
- IMDSv2 enforcement on all EC2 instances (blocks SSRF credential theft).
- SSM-backed `.env` injection on boot — secrets never committed to git.
- ALB with `slow_start=900` and 60s health check interval to handle 15-25 min boot times.
- Section-aware semantic chunking (600-char target, 100-char overlap, 100-char minimum).
- Embeddings factory (`api/services/embeddings/factory.py`) with `make_embeddings_client`.
- Langfuse prompt version management in agentic RAG.
- Neo4j graph config integration in `AgenticRAGService`.
- Dagster/Prefect containers updated to Python 3.12.
- `deepeval`, `neo4j`, `instructor` dependencies added to `pyproject.toml`.

### Changed
- Airflow indexing (`nuke_ingestion/indexing.py`) refactored to section-aware chunking pipeline.
- Agentic RAG tools, factory, and state updated for Neo4j and thread stability.
- Evaluation harness and persistence updated for new evaluation schema.
- `docker-compose.yaml` simplified for local development (nginx removed).
- Orchestrators updated for Airflow 3.x `providers.standard` import path.

### Removed
- Telegram service (`api/services/telegram/`) — removed entirely.
- Nginx from docker-compose (replaced by AWS ALB in cloud deployment).

### Fixed
- `test_ray_indexing.py` patch path updated after embeddings factory refactor.
- Langfuse media upload endpoint corrected to `http://langfuse-minio:9000` (was broken `localhost`).
- IAM `kms:Decrypt` scope tightened to `arn:aws:kms:*:*:alias/aws/ssm`.
- `.env` file `chmod 600` added in all user_data boot scripts.
