#!/usr/bin/env python3
"""Generate branded GitHub profile stat cards as self-contained SVGs.

Data: GitHub REST (user, repos) + GraphQL (contribution calendar) + RubyGems.
Auth: GITHUB_TOKEN env var if set (GitHub Actions), else falls back to `gh api`.

Outputs (into --out dir):
  overview.svg       — stat tiles: contributions, repos, stars, gem downloads
  contributions.svg  — 12-month contribution heatmap (sequential cyan ramp)
  languages.svg      — language share by code size (horizontal bars)

Palette: categorical #0891b2/#7c3aed/#db2777/#b45309 on surface #0d1130 —
validated (lightness band, chroma, CVD, normal-vision, contrast) 5 Aug 2026.
"""

import json
import os
import subprocess
import sys
import urllib.request
from datetime import datetime

USER = "developerJai"
GEM = "groww-mcp"

SURFACE = "#0d1130"
BORDER = "#2c3a72"
INK = "#e6ecff"
INK2 = "#8b9dc9"
CAT = ["#0891b2", "#7c3aed", "#db2777", "#b45309"]        # validated categorical order
RAMP = ["#1a2350", "#155e75", "#0e7490", "#0891b2", "#22d3ee"]  # sequential cyan (0 → max)
FONT = "-apple-system,'Segoe UI',Helvetica,Arial,sans-serif"


def http_json(url, token=None):
    req = urllib.request.Request(url)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def graphql(query, token=None):
    if token:
        req = urllib.request.Request(
            "https://api.github.com/graphql",
            data=json.dumps({"query": query}).encode(),
            headers={"Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    out = subprocess.run(["gh", "api", "graphql", "-f", f"query={query}"],
                         capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def fetch():
    token = os.environ.get("GITHUB_TOKEN")
    user = http_json(f"https://api.github.com/users/{USER}", token)
    repos = http_json(f"https://api.github.com/users/{USER}/repos?per_page=100", token)
    cal = graphql(
        'query { user(login: "%s") { contributionsCollection { contributionCalendar '
        '{ totalContributions weeks { contributionDays { date contributionCount } } } } } }' % USER,
        token)["data"]["user"]["contributionsCollection"]["contributionCalendar"]
    try:
        gem = http_json(f"https://rubygems.org/api/v1/gems/{GEM}.json")
    except Exception:
        gem = {"downloads": None}
    return user, repos, cal, gem


def svg_card(width, height, body, title):
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{title}">
<rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="12" fill="{SURFACE}" stroke="{BORDER}"/>
<text x="24" y="34" font-family="{FONT}" font-size="15" font-weight="700" fill="{INK}">{title}</text>
{body}
</svg>"""


def fmt(n):
    return f"{n:,}"


def overview_card(user, repos, cal, gem):
    stars = sum(r["stargazers_count"] for r in repos)
    tiles = [
        (fmt(cal["totalContributions"]), "contributions · 12 mo", CAT[0]),
        (fmt(user["public_repos"]), "public repositories", CAT[1]),
        (fmt(stars), "stars earned", CAT[2]),
    ]
    if gem.get("downloads"):
        tiles.append((fmt(gem["downloads"]), f"{GEM} gem downloads", CAT[3]))
    w, h, pad = 830, 138, 24
    tile_w = (w - pad * 2) // len(tiles)
    parts = []
    for i, (num, label, color) in enumerate(tiles):
        x = pad + i * tile_w
        parts.append(f'<rect x="{x}" y="58" width="26" height="4" rx="2" fill="{color}"/>')
        parts.append(f'<text x="{x}" y="94" font-family="{FONT}" font-size="30" font-weight="800" fill="{INK}">{num}</text>')
        parts.append(f'<text x="{x}" y="116" font-family="{FONT}" font-size="12.5" fill="{INK2}">{label}</text>')
    return svg_card(w, h, "\n".join(parts), "GitHub at a glance")


def contributions_card(cal):
    weeks = cal["weeks"]
    counts = [d["contributionCount"] for w in weeks for d in w["contributionDays"]]
    nonzero = sorted(c for c in counts if c > 0)

    def q(p):
        return nonzero[min(int(len(nonzero) * p), len(nonzero) - 1)] if nonzero else 1

    t1, t2, t3 = q(.25), q(.5), q(.75)

    def shade(c):
        if c == 0:
            return RAMP[0]
        if c <= t1:
            return RAMP[1]
        if c <= t2:
            return RAMP[2]
        if c <= t3:
            return RAMP[3]
        return RAMP[4]

    cell, gap, left, top = 11, 3, 52, 58
    w = left + len(weeks) * (cell + gap) + 24
    h = top + 7 * (cell + gap) + 46
    parts = []
    # weekday labels
    for row, lbl in [(1, "Mon"), (3, "Wed"), (5, "Fri")]:
        parts.append(f'<text x="{left - 8}" y="{top + row * (cell + gap) + 9}" text-anchor="end" font-family="{FONT}" font-size="10" fill="{INK2}">{lbl}</text>')
    # month labels + cells
    seen_month = None
    for wi, week in enumerate(weeks):
        x = left + wi * (cell + gap)
        first = week["contributionDays"][0]["date"]
        mon = datetime.strptime(first, "%Y-%m-%d").strftime("%b")
        if mon != seen_month:
            parts.append(f'<text x="{x}" y="{top - 8}" font-family="{FONT}" font-size="10" fill="{INK2}">{mon}</text>')
            seen_month = mon
        for di, day in enumerate(week["contributionDays"]):
            y = top + di * (cell + gap)
            parts.append(f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="2.5" fill="{shade(day["contributionCount"])}"/>')
    # legend + total
    ly = h - 20
    parts.append(f'<text x="{left}" y="{ly + 9}" font-family="{FONT}" font-size="11" fill="{INK2}">{fmt(cal["totalContributions"])} contributions in the last year</text>')
    lx = w - 24 - 5 * (cell + gap) - 66
    parts.append(f'<text x="{lx - 8}" y="{ly + 9}" text-anchor="end" font-family="{FONT}" font-size="10" fill="{INK2}">Less</text>')
    for i, c in enumerate(RAMP):
        parts.append(f'<rect x="{lx + i * (cell + gap)}" y="{ly}" width="{cell}" height="{cell}" rx="2.5" fill="{c}"/>')
    parts.append(f'<text x="{lx + 5 * (cell + gap) + 6}" y="{ly + 9}" font-family="{FONT}" font-size="10" fill="{INK2}">More</text>')
    return svg_card(w, h, "\n".join(parts), "Contribution activity")


def languages_card(repos):
    sizes = {}
    for r in repos:
        if r.get("language"):
            sizes[r["language"]] = sizes.get(r["language"], 0) + max(r.get("size", 0), 1)
    total = sum(sizes.values()) or 1
    langs = sorted(sizes.items(), key=lambda kv: -kv[1])[:4]
    w, pad, row_h, top = 830, 24, 34, 56
    h = top + len(langs) * row_h + 20
    bar_x, bar_w = 150, w - 150 - pad - 110
    parts = []
    for i, (name, kb) in enumerate(langs):
        y = top + i * row_h
        pct = kb / total * 100
        fill_w = max(bar_w * pct / 100, 3)
        color = CAT[i % len(CAT)]
        parts.append(f'<text x="{pad}" y="{y + 13}" font-family="{FONT}" font-size="13" font-weight="600" fill="{INK}">{name}</text>')
        parts.append(f'<rect x="{bar_x}" y="{y}" width="{bar_w}" height="14" rx="4" fill="#1a2350"/>')
        parts.append(f'<rect x="{bar_x}" y="{y}" width="{fill_w:.1f}" height="14" rx="4" fill="{color}"/>')
        parts.append(f'<text x="{bar_x + bar_w + 12}" y="{y + 12}" font-family="{FONT}" font-size="12.5" fill="{INK2}">{pct:.1f}%</text>')
    return svg_card(w, h, "\n".join(parts), "Languages by code size (public repos)")


def main():
    out_dir = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else "assets"
    os.makedirs(out_dir, exist_ok=True)
    user, repos, cal, gem = fetch()
    for name, svg in [("overview.svg", overview_card(user, repos, cal, gem)),
                      ("contributions.svg", contributions_card(cal)),
                      ("languages.svg", languages_card(repos))]:
        path = os.path.join(out_dir, name)
        with open(path, "w") as f:
            f.write(svg)
        print("wrote", path)


if __name__ == "__main__":
    main()
