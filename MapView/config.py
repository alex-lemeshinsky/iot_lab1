import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent

STORE_HOST = os.environ.get("STORE_HOST") or "localhost"
STORE_PORT = int(os.environ.get("STORE_PORT") or 8000)

USER_ID = int(os.environ.get("MAPVIEW_USER_ID") or 1)
MAPVIEW_SOURCE = os.environ.get("MAPVIEW_SOURCE") or "both"
UPDATE_INTERVAL = float(os.environ.get("MAPVIEW_UPDATE_INTERVAL") or 0.4)

CSV_ACCELEROMETER_FILE = os.environ.get("MAPVIEW_ACCELEROMETER_FILE") or str(
    BASE_DIR / "data.csv"
)
CSV_GPS_FILE = os.environ.get("MAPVIEW_GPS_FILE") or str(
    PROJECT_ROOT / "agent" / "src" / "data" / "gps.csv"
)

INITIAL_CSV_POINTS = int(os.environ.get("MAPVIEW_INITIAL_CSV_POINTS") or 20)
STORE_PRELOAD_LIMIT = int(os.environ.get("MAPVIEW_STORE_PRELOAD_LIMIT") or 80)
