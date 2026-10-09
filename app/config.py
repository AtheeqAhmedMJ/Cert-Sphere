import os
from pathlib import Path

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./certs.db")
STORAGE_DIR = Path(os.getenv("STORAGE_DIR", "./storage"))
MAX_RECIPIENTS = int(os.getenv("MAX_RECIPIENTS", "10000"))
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "100"))
MAX_CSV_BYTES = int(os.getenv("MAX_CSV_MB", "10")) * 1024 * 1024
