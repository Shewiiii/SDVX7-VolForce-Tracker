import logging
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
GAME_ROOT = REPO_ROOT.parent
CACHE_DIR = Path("cache")

SCORE_LOG_PATH = str(REPO_ROOT / "score_log.txt")
MUSIC_DB_PATH = str(GAME_ROOT / "data" / "others" / "music_db.xml")
PULLING_RATE = 1

USERNAME = "the player"

DIFF_NAMES = {
    0: "NOV",
    1: "ADV",
    2: "EXH",
    3: "INF/VVD",
    4: "MXM",
    5: "ULT",
}
EXCLUDE_DIFF_IN_HISTORY = "NOV"  # and under. Set it to None to disable

PERFORMANCE_IMAGE_WIDTH = 3000
PERFORMANCE_IMAGE_HEIGHT = 1520

PERFORMANCE_BACKGROUND_PATH = REPO_ROOT / "img" / "performance-background.png"
PERFORMANCE_BACKGROUND_BLUR = 10
PERFORMANCE_BACKGROUND_DIM = 0.67
PERFORMANCE_PANEL_DIM = 0.65

PERFORMANCE_TEXT_COLOR = "#dbddfe"
PERFORMANCE_ACCENT_COLOR = "#cba6f7"
PERFORMANCE_DIM_COLOR = "#6e5b88"
PERFORMANCE_BACKGROUND_COLOR = "#1e1e2e"
PERFORMANCE_PANEL_COLOR = "#1b1b29"
PERFORMANCE_GRID_COLOR = "#303043"
PERFORMANCE_BEST_COLOR = "#49415c"
PERFORMANCE_AVG_10_COLOR = "#8e73ad"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logging.getLogger("urllib3.connectionpool").setLevel(logging.ERROR)
