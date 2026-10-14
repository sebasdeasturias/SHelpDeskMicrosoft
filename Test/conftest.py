import sys
from pathlib import Path

TEST_DIR = Path(__file__).resolve().parent
ROOT = TEST_DIR.parent
BACKEND = ROOT / "backend"

for path in (TEST_DIR, ROOT, BACKEND):
    sp = str(path)
    if sp not in sys.path:
        sys.path.insert(0, sp)
