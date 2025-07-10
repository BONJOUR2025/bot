from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Path to JSON storage for employees
DATA_FILE: Path = BASE_DIR / 'user.json'
