"""Regenerates README.md's Key findings bullets from the latest key_findings_history.json snapshot.

Run after key_findings.ipynb so the snapshot it just wrote is on disk. Every
bullet is built from stored numbers only, never hand-written, so the README
stays in sync with whatever the notebook actually computed.
"""
import json
from pathlib import Path

HISTORY_PATH = Path(__file__).resolve().parent / "key_findings_history.json"
README_PATH = Path(__file__).resolve().parent.parent / "README.md"
START_MARKER = "<!-- KEY_FINDINGS_START -->"
END_MARKER = "<!-- KEY_FINDINGS_END -->"


def describe_change(current, prev, prev_date, unit="pts", decimals=1):
    if prev is None:
        return "not yet trackable, this is the first tracked snapshot"
    delta = current - prev
    if round(delta, decimals) == 0:
        return f"flat versus last week's {prev:.{decimals}f}{unit} ({prev_date})"
    direction = "up" if delta > 0 else "down"
    return f"{direction} {abs(delta):.{decimals}f}{unit} versus last week's {prev:.{decimals}f}{unit} ({prev_date})"


def concentration_band(hhi):
    if hhi > 2500:
        return "highly concentrated"
    if hhi > 1500:
        return "moderately concentrated"
    return "unconcentrated"


def build_bullets(current, prev):
    bullets = []

    s1 = current["section_1"]
    p1 = prev["section_1"] if prev else None
    direction = "outperformed" if s1["spread_pts"] > 0 else "underperformed"
    change = describe_change(s1["spread_pts"], p1["spread_pts"] if p1 else None, prev["date"] if prev else None)
    bullets.append(
        f"- The AI basket has {direction} the S&P 500 by **{s1['spread_pts']:+.1f} points** over the trailing year "
        f"({s1['ai_total_pct']:+.1f}% vs. {s1['bench_total_pct']:+.1f}%). The spread is {change}."
    )

    s2 = current["section_2"]
    p2 = prev["section_2"] if prev else None
    change = describe_change(s2["gap_pts"], p2["gap_pts"] if p2 else None, prev["date"] if prev else None)
    bullets.append(
        f"- Routine day-to-day AI-sector search attention shows no reliable link to stock moves (strongest lag "
        f"correlation only {s2['best_corr']:+.2f}), but the biggest attention spikes show a **{s2['gap_pts']:+.1f}-point** "
        f"swing between the return before and after each one. That swing is {change}."
    )

    s3 = current["section_3"]
    p3 = prev["section_3"] if prev else None
    change = describe_change(s3["top_share_pct"], p3["top_share_pct"] if p3 else None, prev["date"] if prev else None, unit="%")
    bullets.append(
        f"- **{s3['top_symbol']}** still accounts for **{s3['top_share_pct']:.0f}%** of the AI basket's trading volume, "
        f"though the basket-wide Herfindahl index of {s3['hhi']:.0f} is now {concentration_band(s3['hhi'])} overall. "
        f"{s3['top_symbol']}'s share is {change}."
    )

    s4 = current["section_4"]
    p4 = prev["section_4"] if prev else None
    change = describe_change(s4["typical_count"], p4["typical_count"] if p4 else None, prev["date"] if prev else None, unit=" sectors", decimals=0)
    exceptions = ", ".join(s4["exceptions"]) if s4["exceptions"] else "no sector"
    bullets.append(
        f"- **{s4['typical_count']} of {s4['total_sectors']}** sectors fell on rising-yield days and rallied on "
        f"falling-yield days as expected, with {exceptions} the exception. The count following the pattern is {change}."
    )

    s5 = current["section_5"]
    p5 = prev["section_5"] if prev else None
    change = describe_change(s5["latest_vol_pct"], p5["latest_vol_pct"] if p5 else None, prev["date"] if prev else None, unit="%", decimals=2)
    bullets.append(
        f"- Realized volatility peaked at **{s5['max_vol_pct']:.1f}%** on {s5['max_date']} and has since eased to "
        f"**{s5['latest_vol_pct']:.2f}%** as of the latest reading. The latest reading is {change}."
    )

    s6 = current["section_6"]
    p6 = prev["section_6"] if prev else None
    change = describe_change(s6["gap_pts"], p6["gap_pts"] if p6 else None, prev["date"] if prev else None)
    bullets.append(
        f"- The infrastructure names added to the AI basket returned **{s6['infra_final_pct']:+.1f}%** on an "
        f"equal-weighted basis versus **{s6['core_final_pct']:+.1f}%** for the original core cohort, though "
        f"{s6['n_infra_negative']} of those infrastructure names are actually down over the same window. The gap is {change}."
    )

    return bullets


def main():
    history = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
    current = history[-1]
    prev = history[-2] if len(history) > 1 else None

    block = "\n".join(build_bullets(current, prev))

    readme = README_PATH.read_text(encoding="utf-8")
    start = readme.index(START_MARKER) + len(START_MARKER)
    end = readme.index(END_MARKER)
    new_readme = readme[:start] + "\n" + block + "\n" + readme[end:]
    README_PATH.write_text(new_readme, encoding="utf-8")
    print(f"Updated README.md Key findings section from the {current['date']} snapshot.")


if __name__ == "__main__":
    main()
