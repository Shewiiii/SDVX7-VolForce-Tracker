import json
import math
from datetime import datetime, timezone
from pathlib import Path


def load_chart_plays(
    path: str | Path, user_id: int, music_id: int, difficulty: int
) -> list[dict]:
    plays = []
    try:
        stream = open(path, encoding="utf-8")  # noqa: SIM115
    except FileNotFoundError:
        return []
    with stream:
        for line in stream:
            try:
                record = json.loads(line)
                if record.get("volforce_source") != "updated":
                    continue
                if int(record.get("user_id", user_id)) != user_id:
                    continue
                if (
                    int(record["music_id"]) != music_id
                    or int(record["diff_idx"]) != difficulty
                ):
                    continue
                score, clear = int(record["score"]), int(record["clear_type"])
                if not 0 < score <= 10000000 or not 1 <= clear <= 6:
                    continue
                timestamp = datetime.fromisoformat(
                    record["received_at"].replace("Z", "+00:00")
                )
                if timestamp.tzinfo is None:
                    timestamp = timestamp.replace(tzinfo=timezone.utc)
                vf = float(record["volforce"]) / 1000
                if not math.isfinite(vf) or vf < 0:
                    continue
                plays.append(
                    dict(
                        record,
                        score=score,
                        clear_type=clear,
                        timestamp=timestamp.astimezone(timezone.utc),
                        play_vf=vf,
                    )
                )
            except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
                continue
    return sorted(
        plays, key=lambda play: (play["score"], play["timestamp"]), reverse=True
    )


def chart_medal(
    snapshot: dict | None, music_id: int, difficulty: int, plays: list[dict]
) -> int | None:
    if snapshot:
        record = snapshot["chart_records"].get(f"{music_id}:{difficulty}")
        if record is not None:
            return record["clear_type"]
    return max((play["clear_type"] for play in plays), default=None)
