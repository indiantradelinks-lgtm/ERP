"""Shared pytest conftest — loads backend .env so router imports succeed."""
import os
import sys
from pathlib import Path

# Ensure /app/backend is importable for `from core import ...` etc.
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

try:
    from dotenv import load_dotenv
    load_dotenv(BACKEND_DIR / ".env")
except Exception:
    pass

# Hard fallback for unit tests that import core directly
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "erp_database")
