import importlib
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


ROOT = Path(__file__).resolve().parents[1]
DAGS_DIR = ROOT / "orchestrators" / "airflow" / "dags"


def test_airflow_image_installs_airflow_requirements_file():
    dockerfile = (ROOT / "orchestrators" / "airflow" / "Dockerfile").read_text()

    assert "requirements-airflow.txt" in dockerfile
    assert "pip install --no-cache-dir -r /tmp/requirements-airflow.txt" in dockerfile


def test_airflow_requirements_include_task_runtime_dependencies():
    requirements = (ROOT / "orchestrators" / "airflow" / "requirements-airflow.txt").read_text()

    assert "neo4j>=5.0" in requirements
    assert "ray[data]>=2.10" in requirements


def test_nuke_kg_extraction_dag_is_manual_backfill_only(monkeypatch):
    class FakeDAG:
        def __init__(self, dag_id, max_active_runs=None, tags=None, **kwargs):
            self.dag_id = dag_id
            self.max_active_runs = max_active_runs
            self.tags = tags or []
            self.kwargs = kwargs
            self.tasks = []

        def get_task(self, task_id):
            return next(task for task in self.tasks if task.task_id == task_id)

    class FakePythonOperator:
        def __init__(self, task_id, python_callable, dag, **kwargs):
            self.task_id = task_id
            self.python_callable = python_callable
            self.dag = dag
            self.kwargs = kwargs
            self.downstream_list = []
            dag.tasks.append(self)

        def __rshift__(self, other):
            self.downstream_list.append(other)
            return other

    airflow_module = types.ModuleType("airflow")
    airflow_module.DAG = FakeDAG
    python_module = types.ModuleType("airflow.providers.standard.operators.python")
    python_module.PythonOperator = FakePythonOperator

    monkeypatch.setitem(sys.modules, "airflow", airflow_module)
    monkeypatch.setitem(sys.modules, "airflow.providers", types.ModuleType("airflow.providers"))
    monkeypatch.setitem(sys.modules, "airflow.providers.standard", types.ModuleType("airflow.providers.standard"))
    monkeypatch.setitem(
        sys.modules,
        "airflow.providers.standard.operators",
        types.ModuleType("airflow.providers.standard.operators"),
    )
    monkeypatch.setitem(sys.modules, "airflow.providers.standard.operators.python", python_module)
    sys.modules.pop("nuke_kg_extraction", None)

    sys.path.insert(0, str(DAGS_DIR))
    module = importlib.import_module("nuke_kg_extraction")

    dag = module.dag

    assert dag.dag_id == "nuke_kg_extraction"
    assert dag.max_active_runs == 1
    assert dag.kwargs["schedule"] is None
    assert {"nuke", "kg", "neo4j", "backfill"}.issubset(set(dag.tags))

    task_ids = {task.task_id for task in dag.tasks}
    assert task_ids == {"setup_kg_backfill", "extract_all_pending_nuke_kg"}
    assert "scrape_nuke_docs" not in task_ids
    assert "index_nuke_docs" not in task_ids

    extract_task = dag.get_task("extract_all_pending_nuke_kg")
    assert extract_task.python_callable is module.extract_all_pending_nuke_kg

    setup_task = dag.get_task("setup_kg_backfill")
    downstream_ids = {task.task_id for task in setup_task.downstream_list}
    assert downstream_ids == {"extract_all_pending_nuke_kg"}

    db = MagicMock()
    session = MagicMock()
    db.get_session.return_value.__enter__.return_value = session
    repo = MagicMock()
    repo.reset_kg_extracted_for_indexed_pages.return_value = 7

    with (
        patch.object(module, "make_database", return_value=db),
        patch.object(module, "NukePageRepository", return_value=repo),
    ):
        stats = module.setup_kg_backfill(
            dag_run=SimpleNamespace(conf={"reset_kg_extracted": True})
        )

    assert stats == {
        "kg_columns_ready": True,
        "reset_kg_extracted": True,
        "kg_pages_reset": 7,
    }
    repo.reset_kg_extracted_for_indexed_pages.assert_called_once_with()
    db.teardown.assert_called_once_with()
