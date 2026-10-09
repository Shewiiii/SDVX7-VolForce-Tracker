import math

from tracker.timing import judgment_counts, judgment_mode, timing_components


def get_grade_coeff(score: int) -> tuple[float, str]:
    if score >= 9900000:
        return 1.05, "S, ×1.05"
    if score >= 9800000:
        return 1.02, "AAA+, ×1.02"
    if score >= 9700000:
        return 1.00, "AAA, ×1.00"
    if score >= 9500000:
        return 0.97, "AA+, ×0.97"
    if score >= 9300000:
        return 0.94, "AA, ×0.94"
    if score >= 9000000:
        return 0.91, "A+, ×0.91"
    if score >= 8700000:
        return 0.88, "A, ×0.88"
    if score >= 7500000:
        return 0.85, "B, ×0.85"
    if score >= 6500000:
        return 0.82, "C, ×0.82"
    return 0.80, "D, ×0.80"


def get_grade_name(score: int) -> str:
    """Return grade name without the multiplier."""
    return get_grade_coeff(score)[1].partition(",")[0].strip()


def compute_vf(level: float, score: int, clear_coeff: float) -> float:
    grade_coeff, _ = get_grade_coeff(score)
    score_ratio = score / 10000000.0
    raw = level * score_ratio * grade_coeff * clear_coeff * 20.0
    return math.floor(raw) * 0.001


def format_score_breakdown(data: dict) -> str:
    """Display recovered in-game totals and NEAR early/late counter."""
    counts = judgment_counts(data)

    def count(key: str) -> str:
        value = counts.get(key)
        return f"{value:,}" if value is not None else "-"

    if not counts:
        return "Judgment counts were not provided in this result."
    lines = []
    mode = judgment_mode(data)

    if mode is not False and "s_critical" in counts:
        lines.append(f"- S-CRITICAL: {count('s_critical')}")

    critical_label, critical_value = "CRITICAL", count("critical")

    if "critical" not in counts:
        raw = data.get("raw_judgments")
        total = (
            raw.get("critical_including_s_critical") if isinstance(raw, dict) else None
        )
        if type(total) is int and total >= 0:
            critical_label = "CRITICAL (including S-CRITICAL)"
            critical_value = f"{total:,}"
    lines.append(f"- {critical_label}: {critical_value}")

    near = (
        f"{count('early_near')}  |  {count('late_near')}"
        if "early_near" in counts or "late_near" in counts
        else count("near")
    )
    lines.append(f"- NEAR: {near}")
    lines.append(f"- ERROR: {count('error')}")

    components = timing_components(data)
    if components is not None:
        suffix = (
            "(Includes lasers)"
            if components[1]
            == sum(data["timing_histogram"])  # Number of hits == data count in histo
            else ""
        )
        ms = components[0] / components[1]
        early_late = "🐇" if ms > 0 else "🐢" if ms < 0 else "🐈"
        lines.append(f"\nTiming: `{ms:+.1f} ms` {early_late} {suffix}")

    return "\n".join(lines)
