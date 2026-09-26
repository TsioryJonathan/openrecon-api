"""Shared pytest setup.

1. Make the repo root importable regardless of CWD.
2. Force a dummy DATABASE_URL so importing ``app.*`` never depends on (or
   connects to) a real database: engine creation is lazy, no connection is
   attempted at import time. Tests in this suite are hermetic by design.
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ["DATABASE_URL"] = "postgresql+asyncpg://test:test@localhost:5432/test"
