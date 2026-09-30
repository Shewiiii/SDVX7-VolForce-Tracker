import logging
import sys

SCORE_LOG_PATH = "C:/Games/SOUND VOLTEX NABLA/score_log.txt"
PULLING_RATE = 1
MUSIC_DB_PATH = "C:/Games/SOUND VOLTEX NABLA/data/others/music_db.xml"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logging.getLogger("urllib3.connectionpool").setLevel(logging.ERROR)