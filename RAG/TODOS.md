# TODOS

## TODO-1: KG Extraction — Extend to Prefect and Dagster Orchestrators

**What:** Add instructor-based entity extraction (mirroring the Airflow implementation) to `orchestrators/prefect/flows/nuke_ingestion.py` and `orchestrators/dagster/assets/nuke_ingestion.py`.

**Why:** Users running Prefect or Dagster get no KG graph built. Three orchestrators exist; only Airflow gets the feature after this sprint.

**Pros:** Feature parity across all orchestrators. KG extraction works regardless of which orchestrator is active.

**Cons:** ~2x more code, tests for two more codepaths, three places to update if extraction logic changes.

**Context:** Airflow-first is correct now. Extend once orchestrator choice stabilizes and the Airflow implementation is validated. Start from `orchestrators/airflow/dags/nuke_ingestion/indexing.py` as the reference.

**Depends on / blocked by:** instructor-based Airflow extraction (this sprint) must complete and be validated first.

---

## TODO-2: Triple Quality Evaluation — Semantic Correctness of Extracted Triples

**What:** After a full index run, sample ~20 triples from Neo4j and score them for semantic correctness — either via manual inspection or using the existing DeepEval judge model (`gpt-4o-mini`, already wired in `api/evaluation/`).

**Why:** The smoke test gate (>50% produce schema-valid triples) only checks JSON schema validity. `llama3.2:1b` may produce valid-schema triples that are semantically wrong (e.g., `BlurNode ACCEPTS_INPUT ColorNode` when the actual relationship is the opposite). The Neo4j graph's value depends entirely on triple quality.

**Pros:** Catches semantic drift before graph-powered RAG features are built on top of a bad graph. The eval infrastructure (gpt-4o-mini judge, DeepEval) already exists.

**Cons:** Requires a full index run to have triples to sample. Manual inspection takes ~30 min; automated eval requires writing a new golden dataset for graph triples.

**Context:** Only worth doing if you plan to use the graph for actual RAG queries. If the graph is exploratory/visual, schema validity is sufficient. Re-assess after seeing what the graph looks like in the Neo4j browser.

**Depends on / blocked by:** Full Airflow DAG run with `NEO4J__ENABLED=true` completing successfully.
