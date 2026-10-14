from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEST_DIR = Path(__file__).resolve().parent
REPORTS_DIR = TEST_DIR / "reports"
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
DATABASE = ROOT / "database"
STREAMLIT = ROOT / "streamlit_app"
DOCKER = ROOT / "docker"

SKIP_DIRS = {
    ".git",
    "venv",
    ".venv",
    "__pycache__",
    "node_modules",
    "Test",
    ".idea",
    ".vscode",
}

SOURCE_SUFFIXES = {
    ".py",
    ".js",
    ".html",
    ".css",
    ".sql",
    ".yml",
    ".yaml",
    ".json",
    ".sh",
    ".ps1",
}

VEREDICTO_CUMPLE = 80
VEREDICTO_PARCIAL = 50
