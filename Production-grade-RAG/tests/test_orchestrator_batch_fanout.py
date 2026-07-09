from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_prefect_flow_uses_dynamic_index_batch_fanout():
    flow_source = (ROOT / "orchestrators" / "prefect" / "flows" / "nuke_docs_ingestion.py").read_text()

    assert 'name="index_prepare_batches"' in flow_source
    assert 'name="index_nuke_docs_batch"' in flow_source
    assert 'task_run_name="index_batch_{batch_id}"' in flow_source
    assert 'name="index_finalize"' in flow_source
    assert "index_nuke_docs_dynamic()" in flow_source
    assert "index_nuke_docs_batch(page_ids, batch_id)" in flow_source
    assert "index_nuke_docs_batch_task.submit" in flow_source
    assert "index_finalize(batch_results, batch_metadata)" in flow_source
    assert "index_nuke_docs_ray" not in flow_source


def test_dagster_job_uses_dynamic_index_batch_mapping():
    asset_source = (ROOT / "orchestrators" / "dagster" / "assets" / "nuke_ingestion.py").read_text()
    definitions_source = (ROOT / "orchestrators" / "dagster" / "definitions.py").read_text()

    assert "DynamicOut" in asset_source
    assert "DynamicOutput" in asset_source
    assert '@op(name="index_prepare_batches", out=DynamicOut(dict))' in asset_source
    assert '@op(name="index_nuke_docs_batch")' in asset_source
    assert '@op(name="index_finalize")' in asset_source
    assert '@job(name="nuke_docs_ingestion")' in asset_source
    assert ".map(index_nuke_docs_batch_op)" in asset_source
    assert "batch_results.collect()" in asset_source
    assert "index_nuke_docs_dynamic()" in asset_source
    assert "index_nuke_docs_batch(page_ids, batch_id)" in asset_source
    assert "index_nuke_docs_ray" not in asset_source

    assert "define_asset_job" not in definitions_source
    assert "nuke_docs_ingestion_job" in definitions_source
