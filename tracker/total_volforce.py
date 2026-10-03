"""Read the complete chart snapshot captured from the player's login response."""

import json
import logging
from datetime import datetime
from pathlib import Path


def load_total_volforce(path: str | Path) -> dict | None:
    try:
        with open(path, encoding="utf-8") as stream:
            snapshot = json.load(stream)
        if snapshot["source"] != "sv7_load_m" or not snapshot["profile_id"]:
            raise ValueError("Not a complete server snapshot")
        charts = snapshot["chart_volforce"]
        values = list(charts.values())
        if any(type(value) is not int or value < 0 for value in values):
            raise ValueError("Invalid chart VolForce")
        ranked = sorted(charts.items(), key=lambda item: (-item[1], item[0]))[:50]
        total = sum(value for _, value in ranked)

        def chart(entry):
            key, value = entry
            mid, difficulty = map(int, key.split(":"))
            return {"music_id": mid, "diff_idx": difficulty, "volforce": value / 1000}

        records = {}
        for key, record in (snapshot.get("chart_records") or {}).items():
            if key not in charts or not isinstance(record, dict):
                continue
            score, clear = record.get("score"), record.get("clear_type")
            if (
                type(score) is int
                and 0 <= score <= 10000000
                and type(clear) is int
                and 0 <= clear <= 6
            ):
                records[key] = record
        updated_at = datetime.fromisoformat(
            snapshot["updated_at"].replace("Z", "+00:00")
        )
        if updated_at.tzinfo is None:
            raise ValueError("Snapshot time must include a timezone")
        return {
            "value": total / 1000,
            "updated_at": updated_at,
            "chart_count": len(values),
            "song_count": len({key.split(":")[0] for key in charts}),
            "top_count": len(ranked),
            "top_average": total / len(ranked) / 1000 if ranked else None,
            "best_chart": chart(ranked[0]) if ranked else None,
            "worst_top_chart": chart(ranked[-1]) if ranked else None,
            "chart_records": records,
            "player": snapshot.get("player") or {},
            "player_updated_at": snapshot.get("player_updated_at"),
        }
    except FileNotFoundError:
        return None
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as error:
        logging.getLogger(__name__).warning("Cannot read Total VolForce: %s", error)
        return None
