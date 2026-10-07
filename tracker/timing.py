import json
from pathlib import Path


def judgment_mode(record: dict) -> bool | None:
    mode = record.get("s_critical_enabled")
    return mode if type(mode) is bool else None


def judgment_counts(record: dict) -> dict:
    """Read in-game counts."""
    raw_counts = record.get("judgments")
    if not isinstance(raw_counts, dict):
        return {}
    return {
        key: value
        for key, value in raw_counts.items()
        if type(value) is int and value >= 0
    }


def timing_components(record: dict) -> tuple[float, int] | None:
    """Estimate weighted milliseconds, correcting center inflation when possible."""
    histogram = record.get("timing_histogram")
    if (
        not isinstance(histogram, list)
        or len(histogram) != 7
        or any(type(value) is not int or value < 0 for value in histogram)
    ):
        return None
    counts = judgment_counts(record)
    if counts.get("near") != histogram[0] + histogram[6]:
        return None
    hits = sum(histogram)

    raw = record.get("raw_judgments")
    if judgment_mode(record) is True and isinstance(raw, dict):
        just = raw.get("btfx_s_critical")
        total = raw.get("critical_including_s_critical")
        critical = counts.get("critical")
        s_critical = counts.get("s_critical")
        if (
            all(
                type(value) is int and value >= 0
                for value in (just, total, critical, s_critical)
            )
            and total == s_critical + critical
            and just <= s_critical
            and total >= sum(histogram[1:6])
        ):
            side_hits = histogram[1] + histogram[2] + histogram[4] + histogram[5]
            center_hits = just + critical - side_hits
            if 0 <= center_hits <= histogram[3]:
                hits = hits - histogram[3] + center_hits

    if hits == 0:
        return None
    weighted_ms = (
        (histogram[6] - histogram[0]) * 87.5
        + (histogram[5] - histogram[1]) * 37.5
        + (histogram[4] - histogram[2]) * 25.0
    )
    return weighted_ms, hits


def summarize_timing(records: list[dict]) -> dict | None:
    weighted_ms, hits, plays = 0.0, 0, 0
    for record in records:
        components = timing_components(record)
        if components is not None:
            weighted_ms += components[0]
            hits += components[1]
            plays += 1
    if not hits:
        return None
    return {"average_ms": weighted_ms / hits, "hits": hits, "plays": plays}


def load_timing_summary(path: str | Path, user_id: int) -> dict | None:
    """Include timed hits from every captured play, including TRACK CRASH."""
    records = []
    with open(path, encoding="utf-8") as stream:
        for line in stream:
            try:
                record = json.loads(line)
                if int(record.get("user_id", user_id)) == user_id:
                    records.append(record)
            except (ValueError, TypeError, AttributeError):
                continue
    return summarize_timing(records)
