from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_package_imports_from_service_directory_without_pythonpath() -> None:
    """The standalone service entrypoint must resolve repository shared modules."""
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    result = subprocess.run(
        [sys.executable, "-c", "import coordinator_service"],
        cwd=Path(__file__).resolve().parents[1],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
