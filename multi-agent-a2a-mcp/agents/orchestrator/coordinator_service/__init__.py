"""Native A2A coordinator for learner-adaptive course creation."""

import sys
from pathlib import Path

# `shared` lives at the repository root.  Add that root before importing the
# application modules, which also import shared contracts during initialization.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from .app import create_app

__all__ = ["create_app"]
