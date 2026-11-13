#!/usr/bin/env python3
"""Regenerate the profile README cards from live GitHub + PyPI data.

Writes five self-hosted SVGs into assets/:
  header.svg    neofetch-style identity panel
  stats.svg     twelve-month counters and PyPI downloads
  activity.svg  weekly contribution chart with streaks
  heatmap.svg   contribution calendar
  signals.svg   commit rhythm by hour and language split

Then bumps the cache-busting query string on those images in README.md so
GitHub's camo proxy serves the fresh files instead of its cached copies.

Standard library only (urllib), so the GitHub Action needs no dependency
install. A failing source keeps the previous file on disk instead of writing
a card full of zeros.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import os
import pathlib
import re
import sys
import time
import urllib.error
import urllib.request
from xml.sax.saxutils import escape

USER = os.environ.get("GH_USER", "iruzen-dono")
TOKEN = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""
ROOT = pathlib.Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
README = ROOT / "README.md"

# ---- design tokens: one accent, solid fills, no gradients ----------------
BG = "#0d1117"
CARD_BG = "#0f141b"
BORDER = "#232c38"
RULE = "#1b2430"
TEXT = "#e6edf3"
MUTED = "#909dab"
DIM = "#59636e"
ACCENT = "#2f81f7"
GREEN = "#3fb950"
MONO = ("ui-monospace,SFMono-Regular,'SF Mono',Menlo,Consolas,"
        "'Liberation Mono',monospace")

RAMP = ["#141b24", "#0e4429", "#006d32", "#26a641", "#39d353"]

PYPI_PACKAGES = ("hermes-project-oracle", "hermes-memory-vault")
PACKAGE_VERSION = {
    "hermes-project-oracle": "2.3.0",
    "hermes-memory-vault": "0.2.0",
}

LANG_COLORS = {
    "TypeScript": "#3178c6", "JavaScript": "#d9b73a", "Python": "#3572a5",
    "PHP": "#4f5d95", "Blade": "#e2683c", "CSS": "#663399", "HTML": "#d9542b",
    "Shell": "#6fa83a", "Java": "#b07219", "Dockerfile": "#384d54",
    "Vue": "#41b883", "Go": "#00a5c8", "Rust": "#b76e35",
}
OTHER_COLOR = "#3d4652"


def log(msg: str) -> None:
    print(msg, file=sys.stderr)


def fetch(url: str, *, headers=None, data=None, method="GET", timeout=30) -> str:
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Accept", "application/json")
    req.add_header("User-Agent", f"{USER}-profile-readme")
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8")


def gh_graphql(query: str) -> dict:
    if not TOKEN:
        raise RuntimeError("GITHUB_TOKEN is not set")
    body = json.dumps({"query": query}).encode()
    raw = fetch("https://api.github.com/graphql", data=body, method="POST",
                headers={"Authorization": f"bearer {TOKEN}",
                         "Content-Type": "application/json"})
    payload = json.loads(raw)
    if payload.get("errors"):
        raise RuntimeError(f"GraphQL: {payload['errors']}")
    return payload["data"]


# ---------------------------------------------------------------- data

def pypi_downloads() -> dict:
    """Monthly downloads per package, with retry then on-disk fallback.

    pypistats rate-limits aggressively and a 0 on the card would be a lie, so a
    failed refresh keeps the last good numbers and a partial sum is never shown.
    """
    cache_path = ASSETS / "downloads.json"
    cache = {"packages": {}, "total": 0}
    if cache_path.exists():
        try:
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
        except Exception as exc:
            log(f"  ! downloads cache unreadable: {exc}")

    packages, failed = {}, False
    for pkg in PYPI_PACKAGES:
        for attempt in range(3):
            try:
                payload = json.loads(fetch(
                    f"https://pypistats.org/api/packages/{pkg}/recent", timeout=20))
                packages[pkg] = int(payload["data"]["last_month"])
                break
            except Exception as exc:
                if attempt == 2:
                    log(f"  ! pypistats {pkg}: {exc} (keeping cached value)")
                    failed = True
                else:
                    time.sleep(2 + 2 * attempt)

    cached = cache.get("packages") or {}
    if failed or not packages:
        packages = {**cached, **packages}

    if set(packages) == set(PYPI_PACKAGES):
        total = sum(packages.values())
    elif cache.get("total"):
        total = int(cache["total"])
    else:
        total = sum(packages.values())
        log("  ! downloads total is partial — no cached fallback available")

    if not failed and set(packages) == set(PYPI_PACKAGES):
        cache_path.write_text(json.dumps(
            {"packages": packages, "total": total,
             "updated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")},
            indent=2), encoding="utf-8")
    return {"downloads": total, "per_package": packages}


def commit_hours(repos: list[str]) -> dict:
    """Commit timestamps per weekday/hour, from the public commit history."""
    grid = [[0] * 24 for _ in range(7)]
    sample = 0
    for repo in repos:
        page = 1
        while page <= 3:
            try:
                batch = json.loads(fetch(
                    f"https://api.github.com/repos/{USER}/{repo}/commits"
                    f"?author={USER}&per_page=100&page={page}",
                    headers={"Authorization": f"bearer {TOKEN}"}))
            except Exception as exc:
                log(f"  ! commits {repo} p{page}: {exc}")
                break
            if not batch:
                break
            for item in batch:
                stamp = (item.get("commit", {}).get("author") or {}).get("date")
                if not stamp:
                    continue
                when = dt.datetime.fromisoformat(stamp.replace("Z", "+00:00"))
                grid[when.weekday()][when.hour] += 1
                sample += 1
            if len(batch) < 100:
                break
            page += 1
    return {"grid": grid, "sample": sample}


def streaks(days: list[dict]) -> dict:
    counts = [d["contributionCount"] for d in days]
    longest = run = 0
    for count in counts:
        run = run + 1 if count else 0
        longest = max(longest, run)

    # today can legitimately be empty, so drop one trailing zero before counting
    tail = counts[:-1] if counts and counts[-1] == 0 else counts
    current = 0
    for count in reversed(tail):
        if not count:
            break
        current += 1
    return {"current": current, "longest": longest}


def collect() -> dict:
    query = """
    query {
      user(login: "USERNAME") {
        followers { totalCount }
        repositories(first: 100, ownerAffiliations: OWNER, isFork: false) {
          totalCount
          nodes { name stargazerCount forkCount isFork }
        }
        contributionsCollection {
          totalCommitContributions
          totalPullRequestContributions
          totalIssueContributions
          totalPullRequestReviewContributions
          contributionCalendar {
            totalContributions
            weeks { contributionDays { date contributionCount } }
          }
        }
      }
      merged: search(query: "author:USERNAME type:pr is:merged", type: ISSUE, first: 1) { issueCount }
      mergedExternal: search(query: "author:USERNAME type:pr is:merged -user:USERNAME", type: ISSUE, first: 1) { issueCount }
      externalPrs: search(query: "author:USERNAME type:pr -user:USERNAME", type: ISSUE, first: 1) { issueCount }
      externalOpen: search(query: "author:USERNAME type:pr -user:USERNAME is:open", type: ISSUE, first: 1) { issueCount }
      externalRepos: search(query: "author:USERNAME type:pr -user:USERNAME", type: ISSUE, first: 100) {
        nodes { ... on PullRequest { repository { nameWithOwner } } }
      }
    }
    """.replace("USERNAME", USER)

    data = gh_graphql(query)
    user = data["user"]

    repos = [r for r in user["repositories"]["nodes"] if not r["isFork"]]
    languages: dict[str, int] = {}
    lang_repos: dict[str, int] = {}
    for repo in repos:
        try:
            payload = json.loads(fetch(
                f"https://api.github.com/repos/{USER}/{repo['name']}/languages",
                headers={"Authorization": f"bearer {TOKEN}"}))
            for name, size in payload.items():
                languages[name] = languages.get(name, 0) + int(size)
            if payload:
                top = max(payload.items(), key=lambda kv: kv[1])[0]
                lang_repos[top] = lang_repos.get(top, 0) + 1
        except Exception as exc:
            log(f"  ! languages {repo['name']}: {exc}")

    upstream = sorted({node["repository"]["nameWithOwner"]
                       for node in data["externalRepos"]["nodes"]
                       if node and node.get("repository")})

    cal = user["contributionsCollection"]
    days = [d for week in cal["contributionCalendar"]["weeks"]
            for d in week["contributionDays"]]
    weeks = cal["contributionCalendar"]["weeks"]
    weekly = [sum(d["contributionCount"] for d in w["contributionDays"]) for w in weeks]
    week_starts = [w["contributionDays"][0]["date"] for w in weeks]

    rhythm = commit_hours([r["name"] for r in repos])
    dl = pypi_downloads()

    return {
        "followers": user["followers"]["totalCount"],
        "repo_count": user["repositories"]["totalCount"],
        "stars": sum(r["stargazerCount"] for r in repos),
        "forks": sum(r["forkCount"] for r in repos),
        "contributions": cal["contributionCalendar"]["totalContributions"],
        "commits": cal["totalCommitContributions"],
        "prs": cal["totalPullRequestContributions"],
        "issues": cal["totalIssueContributions"],
        "reviews": cal["totalPullRequestReviewContributions"],
        "merged": data["merged"]["issueCount"],
        "merged_external": data["mergedExternal"]["issueCount"],
        "external_prs": data["externalPrs"]["issueCount"],
        "external_open": data["externalOpen"]["issueCount"],
        "upstream_repos": upstream,
        "downloads": dl["downloads"],
        "per_package": dl["per_package"],
        "languages": languages,
        "lang_repos": lang_repos,
        "days": days,
        "weekly": weekly,
        "week_starts": week_starts,
        "active_days": sum(1 for d in days if d["contributionCount"] > 0),
        "recent": [d["contributionCount"] for d in days[-30:]],
        "streaks": streaks(days),
        "rhythm": rhythm,
        "generated": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d"),
    }


# ---------------------------------------------------------------- svg kit

def esc(value) -> str:
    return escape(str(value))


def num(value: int) -> str:
    return f"{value:,}".replace(",", "\u2009")


def nice_max(value: int) -> int:
    """Round a maximum up to a readable axis top (20, 40, 60, 80...)."""
    if value <= 0:
        return 1
    magnitude = 10 ** math.floor(math.log10(value))
    for step in (1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10):
        if value <= step * magnitude:
            return int(step * magnitude)
    return int(10 * magnitude)


def card(width: int, height: int, label: str) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
        f'height="{height}" viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="{esc(label)}">\n'
        f'<rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" '
        f'rx="10" fill="{BG}" stroke="{BORDER}"/>\n'
        f'<rect x="0.5" y="0.5" width="3" height="{height - 1}" rx="1.5" '
        f'fill="{ACCENT}"/>\n'
    )


def txt(x, y, value, size=11, fill=TEXT, anchor="start", weight=None,
        spacing=None, family=MONO, opacity=None) -> str:
    attrs = [f'x="{x}"', f'y="{y}"', f'font-family="{family}"',
             f'font-size="{size}"', f'fill="{fill}"']
    if anchor != "start":
        attrs.append(f'text-anchor="{anchor}"')
    if weight:
        attrs.append(f'font-weight="{weight}"')
    if spacing:
        attrs.append(f'letter-spacing="{spacing}"')
    if opacity is not None:
        attrs.append(f'opacity="{opacity}"')
    return f'<text {" ".join(attrs)}>{esc(value)}</text>\n'


def label(x, y, value, anchor="start", fill=DIM) -> str:
    return txt(x, y, value.upper(), size=9, fill=fill, anchor=anchor,
               spacing=1.6, weight="600")


def fade(delay: float, dur: float = 0.45, dy: int = 0) -> str:
    """Opacity + optional upward slide, frozen at the end."""
    out = (f'<animate attributeName="opacity" from="0" to="1" begin="{delay:.2f}s" '
           f'dur="{dur}s" fill="freeze"/>')
    if dy:
        out += (f'<animateTransform attributeName="transform" type="translate" '
                f'from="0 {dy}" to="0 0" begin="{delay:.2f}s" dur="{dur}s" '
                f'fill="freeze"/>')
    return out


def footer(width, height, generated) -> str:
    return (txt(width - 18, height - 11, f"updated {generated}", size=9,
                fill=DIM, anchor="end")
            + "</svg>\n")


# ---------------------------------------------------------------- cards

def header_svg(d: dict) -> str:
    w, h = 860, 300
    rows = [
        ("location", "Lomé, Togo \u00b7 UTC\u00b10 \u00b7 remote-first"),
        ("role", "full-stack developer \u00b7 ai-agent tooling"),
        ("now", "5 SaaS in production \u00b7 2 packages on PyPI"),
        ("study", "BSc artificial intelligence & big data \u2014 3rd year"),
        ("oss", f"{d['external_prs']} prs on {len(d['upstream_repos'])} external repos "
                f"\u00b7 {d['merged_external']} merged"),
        ("stack", "TypeScript \u00b7 Python \u00b7 Next.js \u00b7 Laravel \u00b7 Postgres"),
        ("pypi", " \u00b7 ".join(f"{k.replace('hermes-', '')} {v}"
                                 for k, v in PACKAGE_VERSION.items())
                 + f" \u00b7 {num(d['downloads'])} dl / 30d"),
    ]

    out = [card(w, h, "jules zhou — profile")]
    out.append(f'<clipPath id="intro"><rect x="30" y="40" width="0" height="86">'
               f'<animate attributeName="width" from="0" to="600" begin="0.15s" '
               f'dur="0.7s" fill="freeze"/></rect></clipPath>\n')

    # monogram tile
    out.append(f'<g opacity="0"><animate attributeName="opacity" from="0" to="1" '
               f'begin="0.05s" dur="0.4s" fill="freeze"/>\n')
    out.append(f'<rect x="30" y="42" width="104" height="104" rx="6" '
               f'fill="{CARD_BG}" stroke="{BORDER}"/>\n')
    out.append(txt(82, 108, "JZ", size=38, fill=TEXT, anchor="middle",
                   weight="700", spacing=1))
    out.append("</g>\n")
    out.append(txt(82, 166, "iruzen-dono", size=9, fill=DIM, anchor="middle",
                   spacing=1.4))

    # identity
    out.append('<g clip-path="url(#intro)">\n')
    out.append(txt(160, 74, "jules zhou", size=26, weight="700", spacing=-0.4))
    out.append(txt(160, 94, "I build the unglamorous half of agent reliability:",
                   size=11, fill=MUTED))
    out.append(txt(160, 110, "give the model the right context, break the build when it rots.",
                   size=11, fill=MUTED))
    out.append("</g>\n")
    out.append(f'<line x1="160" y1="126" x2="{w - 30}" y2="126" stroke="{RULE}"/>\n')

    y = 150
    for index, (key, value) in enumerate(rows):
        delay = 0.55 + index * 0.075
        out.append(f'<g opacity="0" transform="translate(-6,0)">{fade(delay, 0.35)}\n')
        out.append(f'<animateTransform attributeName="transform" type="translate" '
                   f'from="-6 0" to="0 0" begin="{delay:.2f}s" dur="0.35s" fill="freeze"/>\n')
        out.append(txt(160, y, key, size=9, fill=ACCENT, spacing=1.6, weight="600"))
        out.append(txt(258, y, value, size=11.5, fill=TEXT))
        out.append("</g>\n")
        y += 21

    # 30-day strip: the recent shape of the work, next to the identity block
    recent = d.get("recent") or []
    if recent:
        x0, x1, base, ceiling = 660, 832, 272, 214
        peak = max(recent) or 1
        pitch = (x1 - x0) / len(recent)
        out.append(label(x0, 150, "last 30 days", fill=MUTED))
        out.append(txt(x1, 152, num(sum(recent)), size=18, weight="700", anchor="end"))
        out.append(f'<line x1="{x0}" y1="{base}" x2="{x1}" y2="{base}" stroke="{RULE}"/>\n')
        for index, value in enumerate(recent):
            height = max((value / peak) * (base - ceiling), 2)
            delay = 0.75 + index * 0.02
            out.append(
                f'<g transform="translate({x0 + index * pitch:.1f},{base})">'
                f'<rect x="0" y="{-height:.1f}" width="{max(pitch - 2, 2):.1f}" '
                f'height="{height:.1f}" rx="1" fill="{ACCENT}" fill-opacity="0.85" '
                f'transform="scale(1,0)">'
                f'<animateTransform attributeName="transform" type="scale" '
                f'values="1,0;1,1" begin="{delay:.2f}s" dur="0.4s" fill="freeze"/>'
                f'</rect></g>\n'
            )
    return "".join(out) + footer(w, h, d["generated"])


def stats_svg(d: dict) -> str:
    w, h = 860, 210
    blocks = [
        (num(d["contributions"]), "contributions", "last 12 months"),
        (num(d["commits"]), "commits", f"{round(d['commits'] / 52)} per week"),
        (num(d["merged"]), "prs merged", f"{d['merged_external']} upstream"),
        (num(d["repo_count"]), "public repos", f"{num(d['stars'])} stars \u00b7 {num(d['forks'])} forks"),
        (num(d["external_prs"]), "external prs", f"{d['external_open']} still open"),
        (num(d["downloads"]), "pypi / 30d", f"{len(d['per_package'])} packages"),
    ]
    out = [card(w, h, "GitHub statistics, last twelve months")]
    out.append(label(30, 30, "github signal \u00b7 rolling 12 months"))

    # pypi split, right aligned on the header line
    per = d["per_package"]
    if per:
        split = "  ".join(f"{k.replace('hermes-', '')} {num(v)}" for k, v in per.items())
        out.append(txt(w - 30, 30, split, size=9, fill=DIM, anchor="end"))

    cols, rows = 3, 2
    cell_w, cell_h = (w - 40) // cols, 72
    for index, (value, name, sub) in enumerate(blocks):
        col, row = index % cols, index // cols
        x = 30 + col * cell_w
        y = 56 + row * cell_h
        delay = 0.12 + index * 0.06
        out.append(f'<g opacity="0">{fade(delay)}')
        out.append(txt(x, y + 30, value, size=30, weight="700", spacing=-1))
        out.append(txt(x, y + 48, name, size=9.5, fill=MUTED, spacing=1.3))
        out.append(txt(x, y + 62, sub, size=9, fill=DIM))
        out.append("</g>\n")
        if col:
            out.append(f'<line x1="{x - 14}" y1="{y + 6}" x2="{x - 14}" y2="{y + 58}" '
                       f'stroke="{RULE}"/>\n')
    return "".join(out) + footer(w, h, d["generated"])


def activity_svg(d: dict) -> str:
    w, h = 860, 290
    weekly = d["weekly"] or [0]
    streak = d["streaks"]
    out = [card(w, h, "Weekly contributions with streaks")]

    # streak block, right
    for index, (value, name) in enumerate((
            (f"{streak['current']}d", "current streak"),
            (f"{streak['longest']}d", "longest streak"),
            (num(d["active_days"]), "active days"))):
        bx = w - 30 - (2 - index) * 150
        out.append(f'<g opacity="0">{fade(0.3 + index * 0.08)}')
        out.append(txt(bx, 46, value, size=22, weight="700", anchor="end", spacing=-0.6))
        out.append(txt(bx, 62, name, size=9, fill=DIM, anchor="end", spacing=1.2))
        out.append("</g>\n")
        if index:
            out.append(f'<line x1="{bx + 24}" y1="26" x2="{bx + 24}" y2="58" '
                       f'stroke="{RULE}"/>\n')

    out.append(label(30, 30, "weekly contributions"))
    out.append(txt(30, 46, "last 53 weeks", size=9, fill=DIM))

    # plot area
    left, right, top, bottom = 30, w - 30, 82, h - 54
    peak = max(weekly) or 1
    scale = nice_max(peak)
    step = (right - left) / max(len(weekly) - 1, 1)

    def point(position: int, value: int) -> tuple[float, float]:
        x = left + position * step
        y = bottom - (value / scale) * (bottom - top)
        return x, y

    for fraction in (0.25, 0.5, 0.75, 1.0):
        y = bottom - fraction * (bottom - top)
        out.append(f'<line x1="{left}" y1="{y:.1f}" x2="{right}" y2="{y:.1f}" '
                   f'stroke="{RULE}" stroke-dasharray="2 4"/>\n')
        out.append(txt(left - 6, y + 3, num(round(scale * fraction)), size=8,
                       fill=DIM, anchor="end"))

    points = [point(i, v) for i, v in enumerate(weekly)]
    line = "M " + " L ".join(f"{x:.1f} {y:.1f}" for x, y in points)
    area = line + f" L {points[-1][0]:.1f} {bottom} L {points[0][0]:.1f} {bottom} Z"

    out.append(f'<path d="{area}" fill="{ACCENT}" opacity="0.10">'
               f'<animate attributeName="opacity" from="0" to="0.10" '
               f'begin="0.55s" dur="0.9s" fill="freeze"/></path>\n')
    out.append(f'<path d="{line}" fill="none" stroke="{ACCENT}" stroke-width="1.6" '
               f'stroke-linejoin="round" pathLength="1" stroke-dasharray="1" '
               f'stroke-dashoffset="1">'
               f'<animate attributeName="stroke-dashoffset" from="1" to="0" '
               f'begin="0.15s" dur="1.3s" fill="freeze"/></path>\n')

    last_x, last_y = points[-1]
    out.append(f'<circle cx="{last_x:.1f}" cy="{last_y:.1f}" r="3" fill="{GREEN}" '
               f'opacity="0"><animate attributeName="opacity" from="0" to="1" '
               f'begin="1.35s" dur="0.4s" fill="freeze"/></circle>\n')

    # month ticks, one label per month, never closer than 34px
    seen, last_x = set(), -100.0
    for index, stamp in enumerate(d.get("week_starts") or []):
        try:
            day = dt.date.fromisoformat(stamp)
        except ValueError:
            continue
        if day.month in seen:
            continue
        seen.add(day.month)
        x, _ = point(index, 0)
        if x > right - 26 or x - last_x < 34:
            continue
        last_x = x
        out.append(txt(x, bottom + 16, day.strftime("%b").lower(), size=9, fill=DIM))

    out.append(txt(left, h - 16, f"peak {num(peak)} contributions in a week",
                   size=9, fill=DIM))
    return "".join(out) + footer(w, h, d["generated"])


def heatmap_svg(d: dict) -> str:
    days = d["days"]
    if not days:
        return ""
    columns: list[list] = []
    current: list = [None] * 7
    for entry in days:
        weekday = dt.date.fromisoformat(entry["date"]).weekday()
        if weekday == 0 and any(current):
            columns.append(current)
            current = [None] * 7
        current[weekday] = entry
    if any(current):
        columns.append(current)

    counts = sorted(e["contributionCount"] for e in days if e["contributionCount"] > 0)
    if counts:
        cuts = [counts[min(int(len(counts) * f), len(counts) - 1)] for f in (0.35, 0.62, 0.85)]
    else:
        cuts = [1, 2, 3]

    def shade(count: int) -> str:
        if count <= 0:
            return RAMP[0]
        if count <= cuts[0]:
            return RAMP[1]
        if count <= cuts[1]:
            return RAMP[2]
        if count <= cuts[2]:
            return RAMP[3]
        return RAMP[4]

    pitch, size, left, top = 14, 11, 44, 62
    w = 860
    h = top + 7 * pitch + 50
    out = [card(w, h, "Contribution calendar, last twelve months")]
    out.append(label(30, 26, "contribution calendar"))
    out.append(txt(w - 30, 26, f"{num(d['contributions'])} in the last year",
                   size=9, fill=DIM, anchor="end"))

    last_month = None
    for col, week in enumerate(columns):
        stamps = [e["date"] for e in week if e]
        if not stamps:
            continue
        first = dt.date.fromisoformat(min(stamps))
        if first.month != last_month:
            last_month = first.month
            out.append(txt(left + col * pitch, top - 12, first.strftime("%b").lower(),
                           size=9, fill=DIM))

    for row, name in ((0, "mon"), (2, "wed"), (4, "fri")):
        out.append(txt(left - 8, top + row * pitch + 9, name, size=8, fill=DIM,
                       anchor="end"))

    index = 0
    for col, week in enumerate(columns):
        for row, entry in enumerate(week):
            if entry is None:
                continue
            delay = 0.10 + min(index * 0.0028, 2.0)
            out.append(f'<rect x="{left + col * pitch}" y="{top + row * pitch}" '
                       f'width="{size}" height="{size}" rx="2" '
                       f'fill="{shade(entry["contributionCount"])}" opacity="0">'
                       f'<animate attributeName="opacity" from="0" to="1" '
                       f'begin="{delay:.2f}s" dur="0.28s" fill="freeze"/></rect>\n')
            index += 1

    legend_y = h - 26
    lx = w - 30 - (5 * 15) - 30
    out.append(f'<text x="{lx - 8}" y="{legend_y + 3}" text-anchor="end" '
               f'font-family="{MONO}" font-size="8" fill="{DIM}">quiet</text>\n')
    for i, colour in enumerate(RAMP):
        out.append(f'<rect x="{lx + i * 15}" y="{legend_y - 8}" width="11" height="11" '
                   f'rx="2" fill="{colour}" stroke="{RULE}"/>\n')
    out.append(f'<text x="{lx + 5 * 15 + 6}" y="{legend_y + 3}" font-family="{MONO}" '
               f'font-size="8" fill="{DIM}">loud</text>\n')
    return "".join(out) + footer(w, h, d["generated"])


def signals_svg(d: dict) -> str:
    grid = d["rhythm"]["grid"]
    sample = d["rhythm"]["sample"]
    languages = d["languages"]
    if not sample and not languages:
        return ""

    w, h = 860, 300
    split = 476
    out = [card(w, h, "Commit rhythm by hour and language split")]
    out.append(label(30, 30, "when I commit"))
    out.append(txt(split - 24, 30, f"{num(sample)} commits", size=9, fill=DIM,
                   anchor="end"))

    # 7 x 24 grid
    cell, gap = 14, 2
    left = 62
    top = 52
    peak = max((max(row) for row in grid), default=0) or 1
    for row, name in enumerate(("mon", "tue", "wed", "thu", "fri", "sat", "sun")):
        y = top + row * (cell + gap)
        out.append(txt(left - 10, y + cell - 3, name, size=8, fill=DIM, anchor="end"))
        for hour in range(24):
            value = grid[row][hour]
            ratio = value / peak
            if value == 0:
                colour, alpha = RAMP[0], 1
            else:
                colour, alpha = ACCENT, 0.22 + 0.78 * (ratio ** 0.6)
            delay = 0.12 + (row * 24 + hour) * 0.0016
            out.append(f'<rect x="{left + hour * (cell + gap)}" y="{y}" width="{cell}" '
                       f'height="{cell}" rx="2" fill="{colour}" fill-opacity="{alpha:.2f}" '
                       f'opacity="0"><animate attributeName="opacity" from="0" to="1" '
                       f'begin="{delay:.2f}s" dur="0.3s" fill="freeze"/></rect>\n')

    for hour in range(0, 24, 6):
        x = left + hour * (cell + gap)
        out.append(txt(x, top + 7 * (cell + gap) + 14, f"{hour:02d}", size=8, fill=DIM))
    out.append(txt(left, h - 16, "local hours, UTC\u00b10", size=9, fill=DIM))

    # divider
    out.append(f'<line x1="{split}" y1="26" x2="{split}" y2="{h - 26}" stroke="{RULE}"/>\n')

    # language rows
    out.append(label(split + 28, 30, "what I write"))
    if languages:
        total = sum(languages.values()) or 1
        ranked = sorted(languages.items(), key=lambda kv: -kv[1])[:7]
        y = 56
        for name, value in ranked:
            share = value / total
            colour = LANG_COLORS.get(name, OTHER_COLOR)
            out.append(f'<g opacity="0">{fade(0.35 + ranked.index((name, value)) * 0.05)}')
            out.append(txt(split + 28, y + 10, name, size=10, fill=TEXT))
            repos_count = d["lang_repos"].get(name, 0)
            note = f"{repos_count} repo" + ("s" if repos_count != 1 else "")
            out.append(txt(split + 132, y + 10, note, size=8, fill=DIM, anchor="end"))
            out.append(f'<rect x="{split + 148}" y="{y}" width="146" height="9" rx="4.5" '
                       f'fill="{RULE}"/>')
            out.append(f'<rect x="{split + 148}" y="{y}" width="{max(146 * share, 2):.1f}" '
                       f'height="9" rx="4.5" fill="{colour}"/>')
            out.append(txt(w - 16, y + 9, f"{share * 100:.0f}%", size=9, fill=DIM,
                           anchor="end"))
            out.append("</g>\n")
            y += 30
    return "".join(out) + footer(w, h, d["generated"])


# ---------------------------------------------------------------- main

def bump_cache_buster(version: str) -> bool:
    if not README.exists():
        return False
    text = original = README.read_text(encoding="utf-8")
    for name in ("header", "stats", "activity", "heatmap", "signals"):
        text = re.sub(rf"(assets/{name}\.svg)(\?v=[^\")\s]*)?", rf"\1?v={version}", text)
    if text != original:
        README.write_text(text, encoding="utf-8")
        return True
    return False


def main() -> int:
    ASSETS.mkdir(parents=True, exist_ok=True)
    log(f"collecting data for {USER} ...")
    try:
        data = collect()
    except Exception as exc:
        log(f"FATAL: could not collect data: {exc}")
        return 1

    log(f"  contributions={data['contributions']} commits={data['commits']} "
        f"merged={data['merged']} upstream={data['merged_external']} "
        f"external={data['external_prs']} repos={data['repo_count']} "
        f"streak={data['streaks']} rhythm={data['rhythm']['sample']} commits sampled")

    written = []
    for name, builder in (("header.svg", header_svg), ("stats.svg", stats_svg),
                          ("activity.svg", activity_svg),
                          ("heatmap.svg", heatmap_svg),
                          ("signals.svg", signals_svg)):
        try:
            svg = builder(data)
        except Exception as exc:
            log(f"  ! {name}: build failed: {exc}")
            continue
        if not svg:
            log(f"  ! {name}: no data, keeping the previous file")
            continue
        (ASSETS / name).write_text(svg, encoding="utf-8", newline="\n")
        written.append(name)

    version = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M")
    bumped = bump_cache_buster(version)
    log(f"wrote {', '.join(written) or 'nothing'}; cache buster {version} "
        f"{'applied' if bumped else 'unchanged'}")
    print(f"SUMMARY {data['contributions']} contributions | {data['commits']} commits "
          f"| {data['merged']} merged ({data['merged_external']} upstream of "
          f"{data['external_prs']} external PRs) | {data['repo_count']} repos | "
          f"{data['downloads']} downloads/30d | streak {data['streaks']['current']}d/"
          f"{data['streaks']['longest']}d")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
