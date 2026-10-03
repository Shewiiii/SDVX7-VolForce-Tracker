"""Read local play history and render a Discord-friendly performance chart."""

import json
import math
from datetime import datetime, timedelta, timezone
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont


def load_play_history(
    log_path: str,
    user_id: int,
    default_user_id: int,
    levels: dict,
    days: int = 0,
) -> list[dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days) if days else None
    plays = []
    clears = {1: 50, 2: 100, 3: 102, 4: 106, 5: 110, 6: 104}
    grades = [
        (9900000, 105),
        (9800000, 102),
        (9700000, 100),
        (9500000, 97),
        (9300000, 94),
        (9000000, 91),
        (8700000, 88),
        (7500000, 85),
        (6500000, 82),
        (0, 80),
    ]
    with open(log_path, encoding="utf-8") as stream:
        for line in stream:
            try:
                record = json.loads(line)
                if int(record.get("user_id", default_user_id)) != user_id:
                    continue
                if int(record["clear_type"]) == 1:
                    continue
                timestamp = datetime.fromisoformat(
                    record["received_at"].replace("Z", "+00:00")
                )
                if timestamp.tzinfo is None:
                    timestamp = timestamp.replace(tzinfo=timezone.utc)
                timestamp = timestamp.astimezone(timezone.utc)
                if cutoff and timestamp < cutoff:
                    continue
                if record.get("volforce_source") == "current_play_formula":
                    vf = float(record["volforce"]) / 1000
                else:
                    # Never plot the game's older best-play VF as a current-play value.
                    mid, difficulty = int(record["music_id"]), int(record["diff_idx"])
                    level = float(levels.get(mid, {}).get(difficulty, 0))
                    score, clear = int(record["score"]), int(record["clear_type"])
                    if level <= 0 or not 0 <= score <= 10000000 or clear not in clears:
                        continue
                    grade = next(
                        factor for threshold, factor in grades if score >= threshold
                    )
                    vf = (
                        round(level * 10)
                        * score
                        * grade
                        * clears[clear]
                        * 20
                        // 1000000000000
                    ) / 1000
                if math.isfinite(vf) and vf >= 0:
                    plays.append(
                        dict(
                            record,
                            music_id=int(record["music_id"]),
                            diff_idx=int(record["diff_idx"]),
                            timestamp=timestamp,
                            play_vf=vf,
                        )
                    )
            except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
                continue
    return sorted(plays, key=lambda play: play["timestamp"])


def best_play_message(record: dict, history: list[dict]) -> str | None:
    """Find the longest top-five period; equal VF shares a rank."""
    if int(record.get("clear_type", 0)) == 1:
        return None
    timestamp = datetime.fromisoformat(record["received_at"].replace("Z", "+00:00"))
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    vf = int(record["volforce"]) / 1000
    periods = [("all time", None), ("3 months", 90), ("month", 30), ("week", 7)]
    ranks = [1] * len(periods)
    for play in history:
        if play["timestamp"] >= timestamp or play["play_vf"] <= vf:
            continue
        age = timestamp - play["timestamp"]
        for index, (_, days) in enumerate(periods):
            if ranks[index] <= 5 and (days is None or age <= timedelta(days=days)):
                ranks[index] += 1
    for (period, _), rank in zip(periods, ranks):
        if rank <= 5:
            ordinal = {1: "Best", 2: "2nd best", 3: "3rd best"}.get(rank, f"{rank}th best")
            return (
                f"{ordinal} play of all time !"
                if period == "all time"
                else f"{ordinal} play of the {period} !"
            )
    return None


def load_performance_history(
    log_path: str,
    user_id: int,
    default_user_id: int,
    levels: dict,
    days: int = 0,
    exclude_under: int | None = None,
) -> list[tuple[datetime, float]]:
    return [
        (play["timestamp"], play["play_vf"])
        for play in load_play_history(log_path, user_id, default_user_id, levels, days)
        if exclude_under is None or play["diff_idx"] > exclude_under
    ]


def render_performance_graph(
    plays: list[tuple[datetime, float]],
    title: str,
    show_hours: bool = False,
    exclude_difficulty: str | None = None,
) -> BytesIO:
    if not plays:
        raise ValueError("No plays to graph")
    image = Image.new("RGB", (1500, 760), "#1e1e2e")
    draw = ImageDraw.Draw(image)

    def font(size: int):
        for filename in ("DejaVuSansMono.ttf", "consola.ttf", "arial.ttf"):
            try:
                return ImageFont.truetype(filename, size)
            except OSError:
                pass
        return ImageFont.load_default(size=size)

    small, regular, heading = font(17), font(21), font(29)
    muted, purple, dim = "#888ba6", "#cba6f7", "#6e5b88"
    draw.text((100, 35), title[:70], font=heading, fill=purple)
    subtitle = "VolForce of a play over time"
    if exclude_difficulty:
        suffix = "" if exclude_difficulty == "NOV" else " and under"
        subtitle += f", {exclude_difficulty}{suffix} excluded"
    draw.text((100, 82), subtitle, font=small, fill=muted)
    left, top, right, bottom = 105, 155, 1410, 600
    draw.rectangle((left, top, right, bottom), fill="#1b1b29")
    start, end = plays[0][0].timestamp(), plays[-1][0].timestamp()
    if end == start:
        start -= 30
        end += 30
    maximum = max(value for _, value in plays)
    minimum = min(value for _, value in plays)
    padding = max((maximum - minimum) * 0.12, 0.015)
    low, high = max(0, minimum - padding), maximum + padding

    def point(timestamp, value):
        return (
            left + (timestamp.timestamp() - start) / (end - start) * (right - left),
            bottom - (value - low) / (high - low) * (bottom - top),
        )

    for index in range(11):
        y = top + index / 10 * (bottom - top)
        draw.line((left, y, right, y), fill="#303043")
        value = high - index / 10 * (high - low)
        draw.text((left - 85, y - 10), f"{value:.3f}", font=small, fill=muted)
    for index in range(6):
        timestamp = datetime.fromtimestamp(
            start + index / 5 * (end - start), timezone.utc
        )
        x = left + index / 5 * (right - left)
        label = timestamp.strftime("%H:%M" if show_hours else "%d-%m-%Y")
        label_width = draw.textlength(label, font=small)
        draw.text((x - label_width / 2, bottom + 16), label, font=small, fill=muted)
    draw.text((left, top - 30), "VF", font=small, fill=muted)

    best = 0
    best_points = []
    for timestamp, value in plays:
        x, y = point(timestamp, value)
        draw.ellipse((x - 3, y - 3, x + 3, y + 3), fill=dim)
        if best_points:
            best_points.append(point(timestamp, best))
        best = max(best, value)
        best_points.append(point(timestamp, best))
    if len(best_points) > 1:
        draw.line(best_points, fill="#49415c", width=2)

    for window, color, width in ((10, "#8e73ad", 3), (100, purple, 4)):
        points = []
        total = 0
        for index, (timestamp, value) in enumerate(plays):
            total += value
            if index >= window:
                total -= plays[index - window][1]
            points.append(point(timestamp, total / min(index + 1, window)))
        if len(points) > 1:
            draw.line(points, fill=color, width=width, joint="curve")
    draw.text(
        (100, 697),
        f"{len(plays):,} plays  |  Best {maximum:.3f}  |  Latest {plays[-1][1]:.3f}",
        font=regular,
        fill=muted,
    )
    for x, label, color in (
        (885, "Plays", dim),
        (1045, "Avg 10", "#8e73ad"),
        (1230, "Avg 100", purple),
    ):
        draw.ellipse((x, 702, x + 10, 712), fill=color)
        draw.text((x + 22, 696), label, font=small, fill=muted)
    output = BytesIO()
    image.save(output, format="PNG")
    output.seek(0)
    return output
