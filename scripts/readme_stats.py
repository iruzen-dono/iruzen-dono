#!/usr/bin/env python3
"""Regenerate the profile stat cards from live GitHub + PyPI data.

Writes assets/stats.svg, assets/heatmap.svg, assets/langs.svg, then bumps the
cache-busting query string on those images in README.md so GitHub's camo proxy
serves the fresh file instead of its cached copy.

Standard library only (urllib) so the GitHub Action needs no dependency install.
If a data source fails, the previous SVG on disk is left untouched rather than
overwritten with zeros.
"""
from __future__ import annotations

import datetime as dt
import json
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

BG = "#0d1117"
BORDER = "#30363d"
TEXT = "#e6edf3"
MUTED = "#8b949e"
DIM = "#6e7681"
ACCENT = "#2f81f7"
MONO = ("ui-monospace,SFMono-Regular,'SF Mono',Menlo,Consolas,"
        "'Liberation Mono',monospace")

PYPI_PACKAGES = ("hermes-project-oracle", "hermes-memory-vault")

# GitHub's contribution ramp, sober and solid (no gradients)
RAMP = ["#161b22", "#0e4429", "#006d32", "#26a641", "#39d353"]

LANG_COLORS = {
    "TypeScript": "#3178c6",
    "JavaScript": "#e3b341",
    "Python": "#3572a5",
    "PHP": "#4f5d95",
    "Blade": "#f05340",
    "CSS": "#663399",
    "HTML": "#e34c26",
    "Shell": "#89e051",
    "Java": "#b07219",
    "Dockerfile": "#384d54",
}


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
    raw = fetch(
        "https://api.github.com/graphql",
        data=body,
        method="POST",
        headers={"Authorization": f"bearer {TOKEN}",
                 "Content-Type": "application/json"},
    )
    payload = json.loads(raw)
    if payload.get("errors"):
        raise RuntimeError(f"GraphQL: {payload['errors']}")
    return payload["data"]


# ---------------------------------------------------------------- data

def pypi_downloads() -> dict:
    """Monthly downloads per package, with retry then on-disk fallback.

    pypistats rate-limits aggressively; a 0 shown on the profile card would be a
    lie, so a failed refresh keeps the last good numbers.
    """
    cache_path = ASSETS / "downloads.json"
    cache = {"packages": {}, "total": 0, "updated": None}
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

    if failed or not packages:
        cached = cache.get("packages") or {}
        packages = {**cached, **packages}

    # never present a partial total: a missing package makes the sum a lie
    if set(packages) == set(PYPI_PACKAGES):
        total = sum(packages.values())
    elif cache.get("total"):
        total = int(cache["total"])
    else:
        total = sum(packages.values())
        log("  ! downloads total is partial — no cached value to fall back on")

    if not failed and set(packages) == set(PYPI_PACKAGES):
        cache_path.write_text(json.dumps(
            {"packages": packages, "total": total,
             "updated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")},
            indent=2), encoding="utf-8")
    return {"downloads": total, "per_package": packages}


def collect() -> dict:
    query = """
    query {
      user(login: "USERNAME") {
        followers { totalCount }
        repositories(first: 100, ownerAffiliations: OWNER, isFork: false) {
          totalCount
          nodes { name stargazerCount isFork }
        }
        contributionsCollection {
          totalCommitContributions
          totalPullRequestContributions
          totalIssueContributions
          contributionCalendar {
            totalContributions
            weeks { contributionDays { date contributionCount } }
          }
        }
      }
      merged: search(query: "author:USERNAME type:pr is:merged", type: ISSUE, first: 1) { issueCount }
      mergedExternal: search(query: "author:USERNAME type:pr is:merged -user:USERNAME", type: ISSUE, first: 1) { issueCount }
      mergedRepos: search(query: "author:USERNAME type:pr is:merged", type: ISSUE, first: 100) {
        nodes { ... on PullRequest { repository { nameWithOwner isFork } } }
      }
    }
    """.replace("USERNAME", USER)

    data = gh_graphql(query)
    user = data["user"]

    repos = [r for r in user["repositories"]["nodes"] if not r["isFork"]]
    languages: dict[str, int] = {}
    for repo in repos:
        try:
            payload = json.loads(fetch(
                f"https://api.github.com/repos/{USER}/{repo['name']}/languages",
                headers={"Authorization": f"bearer {TOKEN}"},
            ))
            for name, size in payload.items():
                languages[name] = languages.get(name, 0) + int(size)
        except Exception as exc:  # a single repo must not sink the run
            log(f"  ! languages {repo['name']}: {exc}")

    upstream = sorted({n["repository"]["nameWithOwner"]
                       for n in data["mergedRepos"]["nodes"]
                       if n and n.get("repository")
                       and not n["repository"]["nameWithOwner"].startswith(USER + "/")})

    dl = pypi_downloads()
    downloads, per_package = dl["downloads"], dl["per_package"]

    cal = user["contributionsCollection"]
    days = [d for week in cal["contributionCalendar"]["weeks"]
            for d in week["contributionDays"]]

    return {
        "followers": user["followers"]["totalCount"],
        "repo_count": user["repositories"]["totalCount"],
        "stars": sum(r["stargazerCount"] for r in repos),
        "contributions": cal["contributionCalendar"]["totalContributions"],
        "commits": cal["totalCommitContributions"],
        "prs": cal["totalPullRequestContributions"],
        "merged": data["merged"]["issueCount"],
        "merged_external": data["mergedExternal"]["issueCount"],
        "upstream_repos": upstream,
        "downloads": downloads,
        "per_package": per_package,
        "languages": languages,
        "days": days,
        "generated": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d"),
    }


# ---------------------------------------------------------------- svg bits

def card_open(width: int, height: int, label: str) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
        f'height="{height}" viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="{escape(label)}">\n'
        f'  <rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" '
        f'rx="10" fill="{BG}" stroke="{BORDER}"/>\n'
        f'  <rect x="0.5" y="0.5" width="3" height="{height - 1}" rx="1.5" '
        f'fill="{ACCENT}"/>\n'
    )


def num(value: int) -> str:
    return f"{value:,}".replace(",", "\u2009")


def stats_svg(d: dict) -> str:
    blocks = [
        (num(d["contributions"]), "CONTRIBUTIONS", "last 12 months"),
        (num(d["merged"]), "MERGED PRS", f"{d['merged_external']} in external repos"),
        (num(d["repo_count"]), "PUBLIC REPOS", f"{num(d['stars'])} stars \u00b7 {num(d['commits'])} commits"),
        (num(d["downloads"]), "PYPI DOWNLOADS", "last 30 days"),
    ]
    width, height, cell = 800, 132, 200
    out = [card_open(width, height, "GitHub statistics")]

    for i, (value, label, sub) in enumerate(blocks):
        x = cell * i
        delay = 0.15 + 0.12 * i
        out.append(
            f'  <g opacity="0" transform="translate(0,6)">\n'
            f'    <animate attributeName="opacity" from="0" to="1" '
            f'begin="{delay:.2f}s" dur="0.45s" fill="freeze"/>\n'
            f'    <animateTransform attributeName="transform" type="translate" '
            f'from="0 6" to="0 0" begin="{delay:.2f}s" dur="0.45s" fill="freeze"/>\n'
        )
        if i:
            out.append(f'    <line x1="{x}" y1="26" x2="{x}" y2="{height - 26}" '
                       f'stroke="{BORDER}"/>\n')
        cx = x + cell // 2
        out.append(
            f'    <text x="{cx}" y="62" text-anchor="middle" font-family="{MONO}" '
            f'font-size="34" font-weight="700" fill="{TEXT}">{escape(value)}</text>\n'
            f'    <text x="{cx}" y="84" text-anchor="middle" font-family="{MONO}" '
            f'font-size="11" letter-spacing="1.4" fill="{ACCENT}">{escape(label)}</text>\n'
            f'    <text x="{cx}" y="102" text-anchor="middle" font-family="{MONO}" '
            f'font-size="10" fill="{DIM}">{escape(sub)}</text>\n'
            f'  </g>\n'
        )

    out.append(
        f'  <text x="{width - 16}" y="{height - 10}" text-anchor="end" '
        f'font-family="{MONO}" font-size="9" fill="{DIM}">'
        f'updated {escape(d["generated"])}</text>\n'
    )
    out.append("</svg>\n")
    return "".join(out)


def heatmap_svg(d: dict) -> str:
    days = d["days"]
    if not days:
        return ""
    # regroup into weeks of 7 rows, honouring each date's real weekday
    columns: list[list[tuple[str, int] | None]] = []
    current: list[tuple[str, int] | None] = [None] * 7
    for entry in days:
        weekday = dt.date.fromisoformat(entry["date"]).weekday()
        if weekday == 0 and any(current):
            columns.append(current)
            current = [None] * 7
        current[weekday] = (entry["date"], entry["contributionCount"])
    if any(current):
        columns.append(current)

    counts = sorted(entry["contributionCount"] for entry in days
                    if entry["contributionCount"] > 0)
    if counts:
        q = [counts[int(len(counts) * f)] for f in (0.35, 0.62, 0.85)]
    else:
        q = [1, 2, 3]

    def shade(count: int) -> str:
        if count <= 0:
            return RAMP[0]
        if count <= q[0]:
            return RAMP[1]
        if count <= q[1]:
            return RAMP[2]
        if count <= q[2]:
            return RAMP[3]
        return RAMP[4]

    pitch, size, left, top = 14, 11, 40, 30
    width = left + len(columns) * pitch + 14
    width = max(width, 760)
    height = top + 7 * pitch + 40
    out = [card_open(width, height, "Contribution heatmap, last 12 months")]

    # month labels
    last_month = None
    for col, week in enumerate(columns):
        dates = [day[0] for day in week if day]
        if not dates:
            continue
        first = dt.date.fromisoformat(min(dates))
        if first.month != last_month:
            last_month = first.month
            out.append(
                f'  <text x="{left + col * pitch}" y="{top - 10}" font-family="{MONO}" '
                f'font-size="10" fill="{MUTED}">'
                f'{first.strftime("%b")}</text>\n'
            )

    for row, label in ((0, "Mon"), (2, "Wed"), (4, "Fri")):
        out.append(
            f'  <text x="{left - 8}" y="{top + row * pitch + 9}" text-anchor="end" '
            f'font-family="{MONO}" font-size="9" fill="{DIM}">{label}</text>\n'
        )

    index = 0
    for col, week in enumerate(columns):
        for row, entry in enumerate(week):
            if entry is None:
                continue
            _, count = entry
            delay = 0.10 + min(index * 0.0032, 2.4)
            out.append(
                f'  <rect x="{left + col * pitch}" y="{top + row * pitch}" '
                f'width="{size}" height="{size}" rx="2" fill="{shade(count)}" '
                f'opacity="0"><animate attributeName="opacity" from="0" to="1" '
                f'begin="{delay:.2f}s" dur="0.3s" fill="freeze"/></rect>\n'
            )
            index += 1

    legend_y = height - 16
    out.append(
        f'  <text x="{left}" y="{legend_y}" font-family="{MONO}" font-size="11" '
        f'fill="{MUTED}">{num(d["contributions"])} contributions in the last year</text>\n'
    )
    lx = width - 20 - (5 * 15) - 34
    out.append(f'  <text x="{lx - 8}" y="{legend_y}" text-anchor="end" '
               f'font-family="{MONO}" font-size="9" fill="{DIM}">less</text>\n')
    for i, colour in enumerate(RAMP):
        out.append(f'  <rect x="{lx + i * 15}" y="{legend_y - 9}" width="11" '
                   f'height="11" rx="2" fill="{colour}" stroke="{BORDER}"/>\n')
    out.append(f'  <text x="{lx + 5 * 15 + 6}" y="{legend_y}" font-family="{MONO}" '
               f'font-size="9" fill="{DIM}">more</text>\n')
    out.append("</svg>\n")
    return "".join(out)


def langs_svg(d: dict) -> str:
    languages = d["languages"]
    if not languages:
        return ""
    total = sum(languages.values()) or 1
    ranked = sorted(languages.items(), key=lambda kv: -kv[1])[:6]
    rest = total - sum(v for _, v in ranked)
    segments = [(name, value) for name, value in ranked]
    if rest > 0:
        segments.append(("Other", rest))

    width, height = 800, 138
    bar_x, bar_y, bar_w, bar_h = 24, 44, width - 48, 14
    out = [card_open(width, height, "Languages by bytes")]

    out.append(
        f'  <clipPath id="barclip"><rect x="{bar_x}" y="{bar_y}" width="0" height="{bar_h}">'
        f'<animate attributeName="width" from="0" to="{bar_w}" begin="0.25s" '
        f'dur="1.05s" fill="freeze"/></rect></clipPath>\n'
        f'  <text x="{bar_x}" y="26" font-family="{MONO}" font-size="11" '
        f'letter-spacing="1.4" fill="{MUTED}">LANGUAGES BY BYTES \u00b7 PUBLIC REPOS</text>\n'
        f'  <g clip-path="url(#barclip)">\n'
    )

    offset = 0.0
    for name, value in segments:
        share = value / total
        colour = LANG_COLORS.get(name, "#484f58")
        out.append(
            f'    <rect x="{bar_x + offset * bar_w:.2f}" y="{bar_y}" '
            f'width="{share * bar_w:.2f}" height="{bar_h}" fill="{colour}"/>\n'
        )
        offset += share
    out.append("  </g>\n")
    out.append(f'  <rect x="{bar_x}" y="{bar_y}" width="{bar_w}" height="{bar_h}" '
               f'rx="7" fill="none" stroke="{BORDER}"/>\n')

    # legend, two columns
    col_w = (width - 48) // 3
    for i, (name, value) in enumerate(segments):
        cx = bar_x + (i % 3) * col_w
        cy = 86 + (i // 3) * 20
        share = 100 * value / total
        colour = LANG_COLORS.get(name, "#484f58")
        out.append(
            f'  <rect x="{cx}" y="{cy - 8}" width="8" height="8" rx="2" fill="{colour}"/>\n'
            f'  <text x="{cx + 14}" y="{cy}" font-family="{MONO}" font-size="11" '
            f'fill="{TEXT}">{escape(name)}</text>\n'
            f'  <text x="{cx + col_w - 18}" y="{cy}" text-anchor="end" '
            f'font-family="{MONO}" font-size="11" fill="{MUTED}">'
            f'{share:.1f}%</text>\n'
        )
    out.append("</svg>\n")
    return "".join(out)


# ---------------------------------------------------------------- main

def bump_cache_buster(version: str) -> bool:
    if not README.exists():
        return False
    text = original = README.read_text(encoding="utf-8")
    for name in ("stats", "heatmap", "langs"):
        text = re.sub(
            rf"(assets/{name}\.svg)(\?v=[^\")\s]*)?",
            rf"\1?v={version}",
            text,
        )
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

    log(f"  contributions={data['contributions']} merged={data['merged']} "
        f"external={data['merged_external']} repos={data['repo_count']} "
        f"stars={data['stars']} downloads={data['downloads']}")

    written = []
    for name, builder in (("stats.svg", stats_svg), ("heatmap.svg", heatmap_svg),
                          ("langs.svg", langs_svg)):
        svg = builder(data)
        if not svg:
            log(f"  ! {name}: no data, leaving previous file in place")
            continue
        (ASSETS / name).write_text(svg, encoding="utf-8", newline="\n")
        written.append(name)

    version = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M")
    bumped = bump_cache_buster(version)
    log(f"wrote {', '.join(written) or 'nothing'}; cache buster {version} "
        f"{'applied' if bumped else 'unchanged'}")

    upstream = ", ".join(data["upstream_repos"]) or "none"
    print(f"SUMMARY {data['contributions']} contributions | {data['merged']} merged PRs "
          f"({data['merged_external']} upstream: {upstream}) | {data['repo_count']} repos "
          f"| {data['stars']} stars | {data['downloads']} PyPI downloads/30d")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
