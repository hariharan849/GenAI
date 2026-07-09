# Nuke Docs Parallel Indexing Implementation Summary

**Date**: 2026-07-05  
**Status**: ✅ COMPLETE (Phase 1 & Phase 3)

---

## Overview

Successfully implemented dynamic batch parallelization for Nuke docs indexing in Airflow. The workflow now:
1. **Dynamically calculates batches** at runtime based on total unindexed pages
2. **Spawns 4 parallel indexing tasks** (one per batch) with no interdependencies
3. **Aggregates results** across all batches after completion
4. **Maintains idempotency** — failed pages retry on next DAG run

---

## Architecture Changes

### Before
```
setup → scrape → save → [index (monolithic Ray pipeline)] → kg_extract → report → cleanup
```

Single `index_nuke_docs_ray()` task processes ALL pages in one Ray pipeline with limited parallelism.

### After
```
setup → scrape → save → [prepare_batches → batch_0 || batch_1 || batch_2 || batch_3 → finalize] → kg_extract → report → cleanup
```

Four batch tasks run in parallel, each processing 1/4 of total pages independently.

---

## Files Modified

### 1. `nuke_ingestion/indexing.py`

#### New Constants (Line 27-30)
```python
DEFAULT_NUM_PODS = 4        # Fixed parallelism level for K8s pod distribution
MIN_BATCH_SIZE = 5          # Minimum pages per batch to avoid excessive pod overhead
```

#### New Function: `_calculate_batches()` (Line 83-104)
- **Purpose**: Split pages into N roughly equal batches
- **Input**: `pages: list[dict]`, `num_pods: int = 4`
- **Output**: `list[list[dict]]` — list of batches
- **Logic**: Ceiling division to handle uneven splits; if pages < pods, fewer batches created
- **Example**: 500 pages + 4 pods → 4 batches of [125, 125, 125, 125]

#### Refactored: `_load_unindexed_pages_from_db()` (Line 398-429)
- **Old signature**: `_load_unindexed_pages_from_db() -> list[dict]`
- **New signature**: `_load_unindexed_pages_from_db(batch_page_ids: list[str] | None = None) -> list[dict]`
- **Change**: Now supports optional filtering by page ID list
- **Use case**: Each batch pod calls with its assigned page IDs to fetch only its pages from DB

#### New Function: `index_nuke_docs_batch()` (Line 648-750)
- **Purpose**: Process a single batch of pages via Ray Data pipeline
- **Parameters**:
  - `batch_page_ids: list[str]` — UUID strings for pages in this batch
  - `batch_id: int` — batch number (0-based) for logging
  - `**context` — Airflow task context
- **Process**:
  1. Initialize Ray cluster
  2. Load pages for batch from DB (using `_load_unindexed_pages_from_db()`)
  3. Run Ray Data pipeline (flat_map → embed → bulk_index)
  4. Mark successfully indexed pages in DB
  5. Shutdown Ray cluster
- **Returns**: Dict with `batch_id`, `pages_indexed`, `chunks_indexed`, `error_page_ids`, `indexed_page_ids`

#### New Function: `index_nuke_docs_dynamic()` (Line 753-785)
- **Purpose**: Orchestrate batch calculation and preparation for parallel execution
- **Process**:
  1. Load ALL unindexed pages from DB
  2. Calculate batch distribution using `_calculate_batches()`
  3. Store batch metadata in Airflow XCom
  4. Return orchestration result
- **Returns**: Dict with `num_pages`, `num_batches`, `batches` (list of batch metadata)
- **XCom Key**: `batch_metadata` (consumed by batch tasks)

---

### 2. `nuke_docs_ingestion.py`

#### Updated Imports (Line 1-21)
```python
from airflow.providers.cncf.kubernetes.operators.kubernetes_pod import KubernetesPodOperator
from airflow.models import Variable
from airflow.models.taskgroup import TaskGroup
from nuke_ingestion.indexing import (
    index_nuke_docs_ray,              # Kept for backward compatibility
    index_nuke_docs_dynamic,          # NEW
    index_nuke_docs_batch,            # NEW
    DEFAULT_NUM_PODS,                 # NEW
)
```

#### New Function: `index_finalize()` (Line 60-120)
- **Purpose**: Aggregate results from all parallel batch tasks
- **Process**:
  1. Pull batch metadata from `index_prepare_batches` XCom
  2. For each batch (0 to num_batches-1):
     - Pull results from `index_batch_N` task
     - Accumulate pages_indexed, chunks_indexed, errors
  3. Log summary statistics
- **Returns**: Dict with `total_pages_indexed`, `total_chunks_indexed`, `total_errors`

#### New Function: `_create_batch_pod_tasks()` (Line 152-258)
- **Purpose**: Dynamically create 4 parallel batch indexing tasks
- **Implementation**:
  - Creates a PythonOperator for each batch (4 total)
  - Each task has `_batch_indexer()` wrapper that:
    1. Pulls batch metadata from XCom
    2. Extracts batch page IDs for its batch_id
    3. Calls `index_nuke_docs_batch(page_ids, batch_id, context)`
  - Tasks run with `execution_timeout=25 minutes` each
- **Returns**: List of 4 PythonOperator tasks ready for DAG

#### New Task: `index_prepare_batches` (Line 140-149)
- **Type**: PythonOperator
- **Callable**: `index_nuke_docs_dynamic`
- **Timeout**: 5 minutes
- **Output**: Stores batch metadata in XCom (key: `batch_metadata`)

#### New Tasks: `index_batch_0`, `index_batch_1`, `index_batch_2`, `index_batch_3` (Generated)
- **Type**: PythonOperator (4 tasks total)
- **Callable**: `_batch_indexer()` (wrapper)
- **Timeout**: 25 minutes each
- **Parallelism**: All 4 run in parallel (no inter-dependencies)
- **Output**: Returns dict with batch results

#### New Task: `index_finalize` (Line 260-266)
- **Type**: PythonOperator
- **Callable**: `index_finalize`
- **Timeout**: 5 minutes
- **Input**: Pulls from all batch tasks via XCom
- **Output**: Returns aggregated statistics

#### Updated DAG Dependencies (Line 295-301)
```python
# Before: setup >> scrape >> save >> index >> kg >> report >> cleanup
# After:
setup_task >> scrape_task >> save_task >> index_prepare_batches
index_prepare_batches >> batch_tasks >> index_finalize_task
index_finalize_task >> kg_task >> report_task >> cleanup_task
```

---

## Data Flow

### Step 1: Preparation
```
save_nuke_pages_to_db (writes pages to DB)
           ↓
index_prepare_batches (calls index_nuke_docs_dynamic)
    - Load all unindexed pages
    - Calculate 4 batches
    - Store batch metadata in XCom: {
        "num_pages": 500,
        "num_batches": 4,
        "batches": [
          {"batch_id": 0, "page_ids": ["uuid1", "uuid2", ...], "page_count": 125},
          {"batch_id": 1, "page_ids": ["uuid126", ...], "page_count": 125},
          ...
        ]
      }
```

### Step 2: Parallel Indexing (4 tasks run concurrently)
```
index_batch_0: Process 125 pages (UUIDs 0-124)
index_batch_1: Process 125 pages (UUIDs 125-249)  ← All run in parallel
index_batch_2: Process 125 pages (UUIDs 250-374)
index_batch_3: Process 125 pages (UUIDs 375-499)

Each task:
  1. Retrieves its page IDs from XCom
  2. Calls index_nuke_docs_batch(page_ids, batch_id)
  3. Returns result to Airflow XCom
```

### Step 3: Finalization
```
index_finalize (runs after all 4 batch tasks complete)
  - Pulls results from index_batch_0, 1, 2, 3 XCom
  - Aggregates: total_pages = 500, total_chunks = ~2000, total_errors = 0
  - Logs summary
  - Returns aggregated stats
```

---

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| **Fixed 4 pods** | Simplifies implementation; can be made configurable later |
| **Dynamic batch sizing** | `total_pages / 4` ensures load balancing |
| **Partial failure OK** | Failed pages retry on next DAG run (matches current model) |
| **Ray per batch** | Each batch initializes its own Ray cluster (avoids complexity of shared head node) |
| **PythonOperator for now** | Simpler for development; can migrate to KubernetesPodOperator for prod |
| **XCom for orchestration** | Standard Airflow pattern for passing metadata between tasks |

---

## Performance Expectations

### Baseline (Current Monolithic Approach)
- 500 pages, single Ray pipeline: ~15 minutes total
- Ray pipeline concurrency: 3 (embed) + 1 (index)

### New Parallelized Approach (Theoretical)
- 4 batches × 125 pages each, parallel execution
- Per-batch time: ~4 minutes (125 pages ÷ 500 pages × 15 min)
- **Total time**: ~6-8 minutes (4 min batch + 1 min prepare + 1 min finalize)
- **Speedup**: ~2-2.5× faster than monolithic approach

### Actual Performance
Will depend on:
- Ray init/shutdown overhead per batch (~10-30 sec)
- Database connection overhead per batch
- Cluster resource availability (CPU cores for Ray workers)

---

## Error Handling

### Partial Failure Scenario
```
Batch 0: ✅ 125 pages indexed
Batch 1: ❌ 2 pages failed (network timeout)
Batch 2: ✅ 125 pages indexed
Batch 3: ✅ 125 pages indexed

Result:
- Finalize task logs: "376 pages indexed, 2 errors"
- Failed 2 pages: Stay nuke_pages_indexed=False in DB
- Next DAG run: Failed pages recalculated in new batch and retried
```

### Complete Batch Failure
```
Batch 1: ❌ Entire batch fails (Ray init error)

Result:
- Airflow task "index_batch_1" fails
- Other batch tasks (0, 2, 3) continue and complete
- Finalize task still runs, aggregates 3/4 batches
- Failed batch pages: Stay unindexed
- Next DAG run: Failed batch recalculated and retried
```

---

## Migration to Kubernetes (Optional Future Work)

To deploy with real Kubernetes parallelism, replace PythonOperator with KubernetesPodOperator:

```python
KubernetesPodOperator(
    task_id=f"index_batch_{batch_id}",
    image="nuke-indexing:latest",  # Custom Docker image
    cmds=["python", "-c"],
    arguments=["from nuke_ingestion.indexing import index_nuke_docs_batch; ..."],
    env_vars={
        "BATCH_ID": str(batch_id),
        "BATCH_PAGE_IDS": json.dumps(page_ids),
        "JINA_API_KEY": "{{ var.value.jina_api_key }}",
    },
    namespace="airflow",
    in_cluster=True,
    resources={"request_memory": "2Gi", "request_cpu": "1"},
)
```

---

## Testing Recommendations

1. **Unit Tests**
   - Verify `_calculate_batches()` correctly splits 500 pages into 4 equal batches
   - Test `index_nuke_docs_batch()` with small test batch (10 pages)

2. **Integration Tests**
   - Run full DAG locally with mocked K8s (PythonOperator)
   - Verify XCom flow works correctly
   - Confirm finalize task aggregates results accurately

3. **Staging Tests (K8s cluster)**
   - Deploy to test K8s cluster
   - Trigger DAG with ~100 unindexed pages
   - Observe 4 batch pods spinning up
   - Kill 1 pod mid-run; verify others complete and failed pages marked for retry

---

## File Checksums

| File | Status | Lines Modified |
|------|--------|-----------------|
| `nuke_ingestion/indexing.py` | ✅ Complete | +170 lines |
| `nuke_docs_ingestion.py` | ✅ Complete | +120 lines |

Both files compiled successfully without syntax errors.

---

## Next Steps

### Immediate (Ready Now)
- Deploy DAG to Airflow and test locally
- Verify batch calculation and XCom flow
- Monitor batch task execution times

### Near-term (Recommended)
- Implement K8s deployment with KubernetesPodOperator
- Create slim Docker image for batch pods
- Add CloudTrace metrics for performance monitoring

### Future Enhancements
- Auto-scaling pod count based on page count or cluster capacity
- Batch retry logic in finalize task
- Performance optimization based on Ray init overhead measurements
