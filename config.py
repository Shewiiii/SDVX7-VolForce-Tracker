import logging
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
GAME_ROOT = REPO_ROOT.parent

SCORE_LOG_PATH = str(REPO_ROOT / "score_log.txt")
MUSIC_DB_PATH = str(GAME_ROOT / "data" / "others" / "music_db.xml")
PULLING_RATE = 1

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logging.getLogger("urllib3.connectionpool").setLevel(logging.ERROR)
