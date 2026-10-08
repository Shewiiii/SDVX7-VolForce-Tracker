import json
import logging
import math
import re
import urllib.request
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

START_PRICES = (
    ("Light Start", 3, 206),
    ("Standard Start with EX-TRACK", 4, 267),
    ("Premium Time (4 songs)", 4, 411),
)


def load_play_count(path: str | Path, user_id: int) -> int:
    """Count local attempts, including crashes and repeated charts."""
    count = 0
    with open(path, encoding="utf-8") as stream:
        for line in stream:
            try:
                record = json.loads(line)
                if (
                    isinstance(record, dict)
                    and int(record.get("user_id", user_id)) == user_id
                ):
                    count += 1
            except (ValueError, TypeError, OverflowError):
                continue
    return count


@lru_cache(maxsize=8)
def _fetch_jpy_rate(currency: str, day: str) -> dict: # Day for cache
    request = urllib.request.Request(
        f"https://api.frankfurter.dev/v2/rate/jpy/{currency.lower()}",
        headers={"User-Agent": "SDVX-VolForce-Tracker", "Accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        data = json.load(response)
    rate = float(data["rate"])
    if (
        data["base"] != "JPY"
        or data["quote"] != currency
        or not math.isfinite(rate)
        or rate <= 0
    ):
        raise ValueError("Invalid JPY exchange rate")
    return {"rate": rate, "date": data["date"]}


def get_jpy_rate(currency: str) -> dict | None:
    """Fetch a daily reference rate without an API key; keep yen on failure."""
    currency = currency.strip().upper()
    if currency == "JPY":
        return {"rate": 1.0, "date": None}
    try:
        if not re.fullmatch(r"[A-Z]{3}", currency):
            raise ValueError("Expected a three-letter ISO currency code")
        return _fetch_jpy_rate(currency, datetime.now(timezone.utc).date().isoformat())
    except (OSError, ValueError, TypeError, KeyError) as error:
        logger.warning(
            "Could not convert spending estimates to %s: %s", currency, error
        )
        return None
