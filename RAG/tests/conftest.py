import sys
from pathlib import Path

# Make nuke_ingestion importable from orchestrators/airflow/dags
sys.path.insert(0, str(Path(__file__).parent.parent / "orchestrators" / "airflow" / "dags"))
