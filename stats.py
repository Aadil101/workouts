"""All-time per-exercise charts, the ones Hevy's free tier cuts off at three months.

Deliberately the same metrics Hevy shows on an exercise's page, so a chart here
can be checked against the app's for any window the app still covers.
"""
import os, sys, html, datetime as dt
from collections import defaultdict
import workouts as w
from plan import mode


# Hevy's rep-to-percentage table, from its help article on estimated 1RM. Not a
# formula: Brzycki, Epley and Lombardi all miss the app's figures by 0.5-2%.
PCT = [100, 97, 94, 92, 89, 86, 83, 81, 78, 75, 73, 71, 70, 68, 67,
       65, 64, 63, 61, 60, 59, 58, 57, 56, 55, 54, 53, 52, 51, 50]


def e1rm(s):
    """Weight over the table's share for that many reps; past 30 stays at 50%."""
    return s.weight / (PCT[min(s.reps, 30) - 1] / 100)


METRICS = {
    "weight": [
        ("Heaviest Weight", "lbs", lambda ss: max(s.weight for s in ss)),
        ("One Rep Max", "lbs", lambda ss: max(e1rm(s) for s in ss)),
        ("Best Set Volume", "lbs", lambda ss: max(s.weight * s.reps for s in ss)),
        ("Session Volume", "lbs", lambda ss: sum(s.weight * s.reps for s in ss)),
        ("Total Reps", "reps", lambda ss: sum(s.reps for s in ss)),
    ],
    "reps": [
        ("Most Reps (Set)", "reps", lambda ss: max(s.reps for s in ss)),
        ("Session Reps", "reps", lambda ss: sum(s.reps for s in ss)),
    ],
    "time": [
        ("Best Time", "time", lambda ss: max(s.duration for s in ss)),
        ("Total Time", "time", lambda ss: sum(s.duration for s in ss)),
    ],
}


def logged(s, m):
    """A set that counts toward its exercise's metrics. Empty rows do not."""
    return bool(s.weight and s.reps) if m == "weight" else bool(s.duration if m == "time" else s.reps)


def series(hist):
    """exercise -> (mode, {metric: [(date, value), ...]}), one point per session."""
    per = defaultdict(lambda: defaultdict(list))
    for day, _, ss in w.sessions(hist):
        for s in ss:
            per[s.exercise][day].append(s)
    out = {}
    for ex, days in per.items():
        m = mode(hist, ex)
        pts = defaultdict(list)
        for day in sorted(days):
            ss = [s for s in days[day] if logged(s, m)]
            if ss:
                for name, _, f in METRICS[m]:
                    pts[name].append((day, f(ss)))
        if pts:
            out[ex] = (m, pts)
    return out


def num(x, unit):
    """Hevy's spelling: '85 lbs', '11 reps', '1min 41s'."""
    if unit != "time":
        return f"{round(x, 1):g} {unit}"
    m, sec = divmod(round(x), 60)
    return " ".join(p for p in (m and f"{m}min", sec and f"{sec}s") if p) or "0s"


def day(d, today=None):
    """'Sep 8', with the year only once it stops being this one."""
    today = today or dt.date.today()
    return f"{d:%b} {d.day}" + (f", {d.year}" if d.year != today.year else "")


def chart(pts, unit, wd=600, ht=150, pad=24):
    """Inline SVG line chart, x scaled by date so gaps between sessions show."""
    xs = [d.timestamp() for d, _ in pts]
    ys = [v for _, v in pts]
    x0, x1 = xs[0], max(xs[-1], xs[0] + 1)
    y0, y1 = min(ys), max(max(ys), min(ys) + 1)
    px = lambda x: pad + (x - x0) / (x1 - x0) * (wd - 2 * pad)
    py = lambda y: ht - pad - (y - y0) / (y1 - y0) * (ht - 2 * pad)
    line = " ".join(f"{px(x):.1f},{py(y):.1f}" for x, y in zip(xs, ys))
    # Each point owns the strip of x nearest to it, so a tap anywhere picks a point
    # however dense the chart gets. CSS :hover rather than script, because the
    # iPhone Files preview does not run JavaScript.
    cuts = [0] + [(px(a) + px(b)) / 2 for a, b in zip(xs, xs[1:])] + [wd]
    pts_svg = "".join(
        f'<g class="pt"><rect x="{l:.1f}" width="{r - l:.1f}" height="{ht}"/>'
        f'<circle cx="{px(x):.1f}" cy="{py(y):.1f}" r="3"/>'
        f'<text class="tip" x="{min(max(px(x), 60), wd - 60):.1f}" y="{max(py(y) - 10, 12):.1f}" text-anchor="middle">'
        f'{num(v, unit)} · {day(d)}</text></g>'
        for x, y, (d, v), l, r in zip(xs, ys, pts, cuts, cuts[1:]))
    return (f'<svg viewBox="0 0 {wd} {ht}" role="img">'
            f'<text x="2" y="{pad - 8}">{num(y1, unit)}</text><text x="2" y="{ht - 4}">{num(y0, unit)}</text>'
            f'<text x="{wd - 2}" y="{ht - 4}" text-anchor="end">{pts[0][0]:%d %b %Y} – {pts[-1][0]:%d %b %Y}</text>'
            f'<polyline points="{line}"/>{pts_svg}</svg>')


PAGE = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Lifting Stats</title>
<style>
:root {{ --bg:#fff; --fg:#1a1a1a; --muted:#777; --line:#2563eb; --rule:#e5e5e5; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#111; --fg:#eee; --muted:#999; --line:#60a5fa; --rule:#333; }} }}
body {{ background:var(--bg); color:var(--fg); font:15px/1.4 system-ui, sans-serif; max-width:640px; margin:0 auto; padding:16px; }}
details {{ border-top:1px solid var(--rule); padding:8px 0; }} summary {{ cursor:pointer; font-weight:600; }}
summary span, .muted {{ color:var(--muted); font-weight:400; }}
table {{ border-collapse:collapse; margin:8px 0; }} td {{ padding:2px 12px 2px 0; }}
h3 {{ font-size:14px; margin:16px 0 0; }}
svg {{ width:100%; height:auto; }} svg text {{ fill:var(--muted); font-size:11px; }}
polyline {{ fill:none; stroke:var(--line); stroke-width:2; }} circle {{ fill:var(--line); }}
.pt {{ cursor:pointer; }} .pt rect {{ fill:transparent; }} .pt .tip {{ visibility:hidden; fill:var(--fg); font-size:13px; font-weight:600; }}
.pt:hover .tip {{ visibility:visible; }} .pt:hover circle {{ r:5; }}
</style></head><body><h1>Lifting Stats</h1><p class="muted">{summary}</p>{body}</body></html>"""


def render(stats):
    blocks = []
    # Most recently trained first, the same order you would scroll for in the app.
    last = lambda ex: next(iter(stats[ex][1].values()))[-1][0]
    for ex in sorted(stats, key=last, reverse=True):
        m, pts = stats[ex]
        first = next(iter(pts.values()))
        prs = "".join(f"<tr><td>{name}</td><td>{num(v, unit)}</td><td class='muted'>{d:%d %b %Y}</td></tr>"
                      for name, unit, _ in METRICS[m]
                      for d, v in [max(pts[name], key=lambda p: (p[1], -p[0].timestamp()))])
        charts = "".join(f"<h3>{name}</h3>{chart(pts[name], unit)}" for name, unit, _ in METRICS[m])
        blocks.append(f"<details><summary>{html.escape(ex)} <span>· {len(first)} sessions, last {first[-1][0]:%d %b}</span></summary>"
                      f"<table>{prs}</table>{charts}</details>")
    return "".join(blocks)


def main():
    hist = w.load_history()
    if not hist:
        sys.exit("no history yet - run ingest.py on a Hevy export first")
    stats = series(hist)
    summary = f"{len(w.sessions(hist))} sessions, {hist[0].date:%d %b %Y} – {hist[-1].date:%d %b %Y}. Records are earliest-first on ties."
    page = PAGE.format(summary=summary, body=render(stats))
    written = [os.path.join(w.DATA, "stats.html")]
    if w.SYNC:
        written.append(os.path.normpath(os.path.join(w.SYNC, "stats.html")))
    for path in written:
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(page)
        except OSError as e:
            print(f"! could not write {path}: {e}", file=sys.stderr)
    print(f"{len(stats)} exercises written to " + ", ".join(written))


if __name__ == "__main__":
    main()
