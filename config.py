import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent
load_dotenv(REPO_ROOT / ".env")
GAME_ROOT = REPO_ROOT.parent

SCORE_LOG_PATH = REPO_ROOT / "cache" / "score_log.txt"
TOTAL_VOLFORCE_CACHE_PATH = REPO_ROOT / "cache" / "total_volforce.json"
VOLFORCE_HISTORY_PATH = REPO_ROOT / "cache" / "volforce_history.jsonl"
MUSIC_DB_PATH = GAME_ROOT / "data" / "others" / "music_db.xml"
PULLING_RATE = 1

USERNAME = os.getenv("TRACKER_USERNAME") or "Shewi"
FOOTER = "SDVX ∇ VolForce Tracker"

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
PERFORMANCE_FONT_PATH = REPO_ROOT / "assets" / "fonts" / "DejaVuSansMono.ttf"

PERFORMANCE_BACKGROUND_PATH = (
    REPO_ROOT / "assets" / "img" / "performance-background.png"
)
PERFORMANCE_BACKGROUND_BLUR = 10
PERFORMANCE_BACKGROUND_DIM = 0.67
PERFORMANCE_PANEL_DIM = 0.65

PERFORMANCE_TEXT_COLOR = "#dbddfe"
PERFORMANCE_ACCENT_COLOR = "#cba6f7"
PERFORMANCE_DIM_COLOR = "#6e5b88"
PERFORMANCE_BACKGROUND_COLOR = "#1e1e2e"
PERFORMANCE_PANEL_COLOR = "#1b1b29"
PERFORMANCE_GRID_COLOR = "#303043"
PERFORMANCE_BEST_COLOR = "#504A72"
PERFORMANCE_AVG_10_COLOR = "#8e73ad"
PERFORMANCE_MINIMUM_COLOR = "#463F46"
PERFORMANCE_TOTAL_COLOR = "#bc7bc5"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logging.getLogger("urllib3.connectionpool").setLevel(logging.ERROR)
