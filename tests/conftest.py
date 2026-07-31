import sys
from pathlib import Path


# Ensure imports like "from app import create_app" work no matter how pytest
# is invoked (console script vs. python -m pytest).
REPO_ROOT = Path(__file__).resolve().parents[1]
repo_root_str = str(REPO_ROOT)
if repo_root_str not in sys.path:
    sys.path.insert(0, repo_root_str)