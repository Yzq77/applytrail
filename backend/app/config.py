"""Runtime configuration, read from environment variables.

Your personal data lives in ``data/applytrail.db`` (git-ignored) unless you point
``APPLYTRAIL_DB`` somewhere else, e.g. an encrypted volume or a synced folder.
"""

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get("APPLYTRAIL_DATA_DIR", REPO_ROOT / "data"))
FRONTEND_DIST = REPO_ROOT / "frontend" / "dist"

DEMO_MODE = os.environ.get("APPLYTRAIL_DEMO") == "1"
GHOST_DAYS_DEFAULT = int(os.environ.get("APPLYTRAIL_GHOST_DAYS", "21"))
# An open application whose current stage hasn't moved for this long is "pending".
PENDING_DAYS_DEFAULT = int(os.environ.get("APPLYTRAIL_PENDING_DAYS", "7"))


def db_path() -> Path:
    explicit = os.environ.get("APPLYTRAIL_DB")
    if explicit:
        return Path(explicit).expanduser()
    return DATA_DIR / ("demo.db" if DEMO_MODE else "applytrail.db")
