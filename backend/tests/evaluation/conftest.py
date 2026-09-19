"""Bootstrap for evaluation-harness tests in the backend test suite.

The harness lives at the repository root under ``evaluation/``, so it must
be added to ``sys.path`` before any ``evaluation.harness`` import.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))