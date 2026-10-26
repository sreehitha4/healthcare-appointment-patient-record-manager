
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
INSTANCE_DIR = BASE_DIR / "instance"

INSTANCE_DIR.mkdir(exist_ok=True)

DATABASE_PATH = INSTANCE_DIR / "healthcare.db"

SECRET_KEY = os.environ.get(
    "SECRET_KEY",
    "development-key-change-before-deployment"
)
