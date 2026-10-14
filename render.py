"""Step 5 — Render the static site from the saved digests.

Reads archive/YYYY-MM-DD/digest.json and writes:
  index.html                       the latest week
  archive/YYYY-MM-DD/index.html    every week, linked from the timeline

Run `python render.py` on its own to tweak layout or CSS without rerunning
the model.

The page layout, theme and CSS are adapted from Neha/ai-trends-agent (MIT):
tilted title block, jump-link pills, hard-shadow cards, right-hand timeline.
"""

from __future__ import annotations

import datetime
import html
import json
import os
import re
import shutil

import config

# Small inline icon so the page stays self-contained.
_ICON_REDDIT = (
    '<svg class="src-icon" viewBox="0 0 20 20" aria-hidden="true">'
    '<circle cx="10" cy="10" r="10" fill="#FF4500"/>'
    '<circle cx="7.2" cy="10.2" r="1.35" fill="#fff"/>'
    '<circle cx="12.8" cy="10.2" r="1.35" fill="#fff"/>'
    '<path d="M7.4 12.4c.8.7 1.7 1 2.6 1s1.8-.3 2.6-1" fill="none" '
    'stroke="#fff" stroke-width="1.2" stroke-linecap="round"/>'
    "</svg>"
)

FONTS = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link href="https://fonts.googleapis.com/css2?family=Fredoka:wght@500;600;700'
    '&family=Nunito:wght@400;600;700;800&display=swap" rel="stylesheet">'
)

CSS = """
:root{--ink:#1a1523;--paper:#fff8ef;--card:#fff;--coral:#ff5a5f;--mango:#ffb703;
--lime:#8fd94f;--teal:#00c2a8;--sky:#4cc9f0;--link:#0b6e4f}
html{scroll-behavior:smooth}
body{margin:0;color:var(--ink);font-family:"Nunito","Trebuchet MS",sans-serif;line-height:1.55;
background-color:#ffe8a3;background-image:
radial-gradient(circle at 12% 18%,#ff8fab55 0 18%,transparent 19%),
radial-gradient(circle at 88% 12%,#4cc9f055 0 16%,transparent 17%),
radial-gradient(circle at 80% 78%,#8fd94f55 0 20%,transparent 21%),
radial-gradient(circle at 18% 82%,#ffb70366 0 14%,transparent 15%),
repeating-linear-gradient(-18deg,#ffe8a3 0 14px,#ffd56b 14px 28px);min-height:100vh}
.page{max-width:1280px;margin:0 auto;padding:2rem 1rem 3rem}
.page-header{margin-bottom:.25rem}
.body-row{display:grid;grid-template-columns:minmax(0,1fr) 160px;gap:1.5rem;align-items:start}
.main{min-width:0}
h1{font-family:"Fredoka","Nunito",sans-serif;font-weight:700;font-size:clamp(2rem,4vw,3rem);
letter-spacing:-.02em;margin:0 0 .85rem;display:inline-block;padding:.2rem .55rem .35rem;
background:var(--ink);color:var(--mango);transform:rotate(-1.2deg);box-shadow:6px 6px 0 var(--coral)}
h2{font-family:"Fredoka","Nunito",sans-serif;font-weight:700;font-size:1.65rem;margin-top:2.5rem;
scroll-margin-top:1rem;display:inline-block;padding:.15rem .55rem;background:var(--mango);
border:2.5px solid var(--ink);box-shadow:4px 4px 0 var(--ink);transform:rotate(-.6deg)}
#by-platform{background:var(--sky)}
#top-threads{background:var(--lime)}
a{color:var(--link)}

.section-nav{margin-bottom:1.25rem}
.section-pills{display:flex;flex-wrap:wrap;gap:.5rem}
.section-pill{display:inline-flex;align-items:center;gap:.35rem;padding:.4rem .8rem;border-radius:12px;
text-decoration:none;font-size:.85rem;font-weight:700;border:2.5px solid var(--ink);color:var(--ink);
background:var(--teal);box-shadow:3px 3px 0 var(--ink);transition:transform .12s ease,box-shadow .12s ease}
.section-pill:nth-child(2){background:var(--mango)}
.section-pill:nth-child(3){background:var(--sky)}
.section-pill:nth-child(4){background:var(--lime)}
.section-pill:hover{transform:translate(-2px,-2px);box-shadow:5px 5px 0 var(--ink);color:var(--ink)}
.section-pill .count{font-size:.72rem;font-weight:800;padding:.1rem .4rem;border-radius:8px;
background:var(--ink);color:var(--mango)}

.date-nav{margin-bottom:1.25rem;padding:.4rem .7rem;border:2.5px solid var(--ink);border-radius:12px;
background:var(--paper);box-shadow:3px 3px 0 var(--coral)}
.date-nav-row{display:flex;align-items:center;justify-content:space-between;gap:.5rem}
.date-current{font-family:"Fredoka","Nunito",sans-serif;font-weight:700;text-align:center;flex:1;
font-size:.95rem;line-height:1.2}
.nav-btn{font-size:.78rem;font-weight:700;text-decoration:none;color:var(--ink);white-space:nowrap;
min-width:5rem;padding:.15rem .35rem;border-radius:8px;border:2px solid transparent;line-height:1.2}
.nav-btn:hover:not(.disabled){background:var(--lime);border-color:var(--ink)}
.date-nav-row .nav-btn:last-child{text-align:right}
.nav-btn.disabled{color:#1a152366;pointer-events:none}

.week-brief{margin:0 0 1.5rem;padding:1.1rem 1.2rem 1.25rem;border:3px solid var(--ink);
border-radius:16px;background:var(--paper);box-shadow:5px 5px 0 var(--teal)}
.week-brief h2{margin-top:0;background:var(--coral);color:#fff}
.week-brief .overview{margin:.85rem 0 .75rem;font-size:1.02rem;font-weight:600}
.week-brief .vs-last{margin:0;display:flex;flex-wrap:wrap;gap:.45rem .55rem;align-items:center;
font-size:.88rem;font-weight:700}
.week-brief .vs-last span{display:inline-block;padding:.2rem .55rem;border:2px solid var(--ink);
border-radius:10px;background:#fff}

.card-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));column-gap:.85rem;row-gap:1.4rem;
margin:.85rem 0 1.25rem}
.card{border:3px solid var(--ink);border-radius:16px;padding:1rem 1.15rem;margin:0;scroll-margin-top:1rem;
display:flex;flex-direction:column;background:var(--card);box-shadow:5px 5px 0 var(--ink);
transition:transform .15s ease,box-shadow .15s ease}
.card:nth-child(4n+1){background:#fff7fb}.card:nth-child(4n+2){background:#f3fffa}
.card:nth-child(4n+3){background:#fffbeb}.card:nth-child(4n+4){background:#f2fbff}
.card:hover{transform:translate(-3px,-3px) rotate(-.5deg);box-shadow:8px 8px 0 var(--coral)}
.card:nth-child(even):hover{transform:translate(-3px,-3px) rotate(.5deg);box-shadow:8px 8px 0 var(--teal)}
.card:target{outline:3px solid var(--mango);outline-offset:3px}
.card h3{margin:0 0 .45rem;font-family:"Fredoka","Nunito",sans-serif;font-weight:600;font-size:1.15rem;
line-height:1.25}
.card p{margin:0 0 .6rem;font-size:.92rem}
.meta{display:flex;flex-wrap:wrap;align-items:center;gap:.45rem .55rem;font-size:.85rem;color:#5a5160;
font-weight:600;margin:0 0 .65rem}
.rank{display:inline-flex;align-items:center;justify-content:center;min-width:1.7rem;height:1.7rem;
padding:0 .35rem;border-radius:999px;background:var(--ink);color:var(--mango);font-family:"Fredoka",sans-serif;
font-weight:700;font-size:.85rem}
.chip{display:inline-flex;align-items:center;padding:.1rem .55rem;border-radius:10px;background:#fff;
border:2px solid var(--ink);font-size:.76rem;font-weight:700;color:var(--ink)}
.chip.playstation{background:var(--sky)}.chip.xbox{background:var(--lime)}.chip.pc{background:var(--mango)}
.badges{display:flex;flex-wrap:wrap;gap:.4rem;margin:0 0 .6rem}
.badge{display:inline-block;padding:.1rem .5rem;border-radius:10px;border:2px solid var(--ink);
font-size:.76rem;font-weight:800;background:#fff}
.badge.new{background:var(--mango)}.badge.up{background:var(--lime)}.badge.down{background:var(--coral);color:#fff}
.top-posts{list-style:none;margin:.2rem 0 .8rem;padding:0;display:grid;gap:.45rem;font-size:.84rem}
.top-posts li{display:flex;gap:.4rem;align-items:flex-start}
.top-posts .t{min-width:0}
.top-posts a{font-weight:700;text-decoration:none;display:-webkit-box;-webkit-line-clamp:2;
-webkit-box-orient:vertical;overflow:hidden}
.top-posts a:hover{text-decoration:underline}
.top-posts small{display:block;color:#5a5160;font-weight:600;font-size:.74rem}
.src-icon{width:1rem;height:1rem;flex-shrink:0;margin-top:.15rem}
.score-row{margin-top:auto;display:flex;align-items:center;gap:.55rem;font-size:.8rem;font-weight:700;
color:#5a5160}
.score{font-family:"Fredoka",sans-serif;font-weight:700;font-size:1.05rem;color:var(--ink);
background:var(--mango);border:2px solid var(--ink);border-radius:10px;padding:.05rem .5rem}

.plat-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:.85rem;margin:.85rem 0 .4rem}
.plat-grid .card{height:auto;padding:.85rem 1rem}
.plat-grid .card:hover{transform:none;box-shadow:5px 5px 0 var(--ink)}
.plat-grid h3{font-size:1.05rem;margin-bottom:.4rem}
.plat-grid ol{margin:0;padding-left:1.2rem;font-size:.92rem;font-weight:600}
.plat-grid small{color:#5a5160}
.thread-list{list-style:none;margin:.85rem 0 0;padding:0}
.thread-list li{display:flex;gap:.6rem;align-items:flex-start;margin:.65rem 0;padding:.75rem 1rem;
background:var(--paper);border:2.5px solid var(--ink);border-radius:14px;box-shadow:3px 3px 0 var(--teal);
font-weight:600;transition:transform .12s ease,box-shadow .12s ease}
.thread-list li:hover{transform:translate(-2px,-2px);box-shadow:5px 5px 0 var(--coral)}
.thread-list .src-icon{margin-top:.2rem}
.thread-list a{font-weight:700}
.thread-list small{display:block;color:#5a5160;font-size:.78rem;font-weight:600}
.note{font-size:.82rem;color:#5a5160;font-weight:600;margin:.2rem 0 0}

.timeline-rail{position:sticky;top:1rem;align-self:start;margin-top:2.5rem}
.timeline-card{border:3px solid var(--ink);border-radius:16px;background:var(--paper);
box-shadow:4px 4px 0 var(--coral);padding:.85rem .75rem 1rem}
.timeline-title{font-family:"Fredoka","Nunito",sans-serif;font-weight:700;font-size:.95rem;margin:0 0 .85rem;
text-align:center;padding:.2rem .4rem;background:var(--mango);border:2px solid var(--ink);border-radius:10px}
.timeline{list-style:none;margin:0;padding:0 0 0 .85rem;position:relative}
.timeline::before{content:"";position:absolute;left:.35rem;top:.35rem;bottom:.35rem;width:3px;
background:var(--ink);border-radius:2px}
.tl-item{position:relative;margin:0 0 1rem;font-weight:700}
.tl-item:last-child{margin-bottom:0}
.tl-dot{position:absolute;left:-.72rem;top:.45rem;width:.7rem;height:.7rem;border-radius:50%;
background:#fff;border:2.5px solid var(--ink);z-index:1}
.tl-item.current .tl-dot{background:var(--coral);box-shadow:0 0 0 3px #ff5a5f44}
.tl-link{display:flex;flex-direction:column;gap:.05rem;padding:.35rem .5rem;border:2px solid transparent;
border-radius:10px;text-decoration:none;color:var(--ink);line-height:1.2}
a.tl-link:hover{background:var(--sky);border-color:var(--ink);color:var(--ink)}
.tl-item.current .tl-link{background:var(--ink);color:var(--mango);border-color:var(--ink)}
.tl-date{font-size:.88rem}.tl-year{font-size:.7rem;opacity:.75;font-weight:600}
.tl-item.current .tl-year{color:#ffe8a3;opacity:1}

footer{margin-top:3rem;padding:1rem 1.1rem;border:3px solid var(--ink);border-radius:16px;background:var(--ink);
color:#ffe8a3;font-size:.9rem;font-weight:600;box-shadow:5px 5px 0 var(--mango)}

@media (max-width:1100px){.card-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media (max-width:860px){
.body-row{grid-template-columns:1fr}
.timeline-rail{position:static;order:-1;margin-top:0;margin-bottom:.5rem}
.timeline{display:flex;flex-wrap:wrap;gap:.5rem;padding:0}.timeline::before{display:none}
.tl-item{margin:0}.tl-dot{display:none}.tl-link{flex-direction:row;align-items:baseline;gap:.35rem}
.plat-grid{grid-template-columns:1fr}}
@media (max-width:640px){.card-grid{grid-template-columns:1fr}h1{transform:none}}
"""

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _e(text) -> str:
    return html.escape(str(text if text is not None else ""), quote=True)


def _nice_date(d: str) -> str:
    try:
        return datetime.date.fromisoformat(d).strftime("%B %d, %Y")
    except ValueError:
        return d


def _short_date(d: str) -> str:
    try:
        return datetime.date.fromisoformat(d).strftime("%b %d")
    except ValueError:
        return d


def _safe_url(url) -> str:
    return url if isinstance(url, str) and url.startswith(("https://", "http://")) else "#"


def _posts(n: int) -> str:
    return f"{n} post" + ("" if n == 1 else "s")


def _compact(n) -> str:
    n = int(n or 0)
    return f"{n / 1000:.1f}k" if n >= 1000 else str(n)


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-") or "game"


def list_dates() -> list:
    """Archived digest dates, oldest first."""
    try:
        return sorted(
            d for d in os.listdir(config.ARCHIVE_DIR)
            if _DATE_RE.match(d) and os.path.isfile(os.path.join(config.ARCHIVE_DIR, d, "digest.json"))
        )
    except OSError:
        return []


def archive_href(target: str, *, from_archive: bool, latest: str) -> str:
    """Relative link from the current page to another week's page."""
    if from_archive:
        return "../../index.html" if target == latest else f"../{target}/"
    return "index.html" if target == latest else f"archive/{target}/"


def _date_nav(current: str, dates: list, from_archive: bool) -> str:
    latest = dates[-1]
    i = dates.index(current) if current in dates else -1
    prev_d = dates[i - 1] if i > 0 else None
    next_d = dates[i + 1] if 0 <= i < len(dates) - 1 else None
    if prev_d:
        prev = (f'<a class="nav-btn" href="{_e(archive_href(prev_d, from_archive=from_archive, latest=latest))}">'
                f"← {_e(_nice_date(prev_d))}</a>")
    else:
        prev = '<span class="nav-btn disabled" aria-disabled="true">← Older</span>'
    if next_d:
        nxt = (f'<a class="nav-btn" href="{_e(archive_href(next_d, from_archive=from_archive, latest=latest))}">'
               f"{_e(_nice_date(next_d))} →</a>")
    else:
        nxt = '<span class="nav-btn disabled" aria-disabled="true">Newer →</span>'
    return (f'<nav class="date-nav" aria-label="Digest date"><div class="date-nav-row">{prev}'
            f'<div class="date-current">{_e(_nice_date(current))}</div>{nxt}</div></nav>')


def _timeline(current: str, dates: list, from_archive: bool) -> str:
    latest = dates[-1]
    items = []
    for d in reversed(dates):
        label = _e(_short_date(d))
        year = _e(d[:4])
        inner = f'<span class="tl-date">{label}</span><span class="tl-year">{year}</span>'
        if d == current:
            items.append(f'<li class="tl-item current"><span class="tl-dot" aria-hidden="true"></span>'
                         f'<span class="tl-link">{inner}</span></li>')
        else:
            href = _e(archive_href(d, from_archive=from_archive, latest=latest))
            items.append(f'<li class="tl-item"><span class="tl-dot" aria-hidden="true"></span>'
                         f'<a class="tl-link" href="{href}">{inner}</a></li>')
    return ('<aside class="timeline-rail" aria-label="Published weeks"><div class="timeline-card">'
            f'<div class="timeline-title">Timeline</div><ol class="timeline">{"".join(items)}</ol></div></aside>')


def _platform_cols(games: list) -> list:
    cols = []
    for pl in config.PLATFORM_ORDER:
        ranked = sorted(
            (g for g in games if pl in g["platforms"]),
            key=lambda g: g["platforms"][pl]["engagement"], reverse=True,
        )[:5]
        if ranked:
            cols.append((pl, ranked))
    return cols


def _section_pills(games: list, cols: list, threads: list) -> str:
    pills = ['<a class="section-pill" href="#week-brief">Brief</a>',
             f'<a class="section-pill" href="#trending-games">Games<span class="count">{len(games)}</span></a>']
    if cols:
        pills.append(f'<a class="section-pill" href="#by-platform">Platforms<span class="count">{len(cols)}</span></a>')
    if threads:
        pills.append(f'<a class="section-pill" href="#top-threads">Threads<span class="count">{len(threads)}</span></a>')
    return f'<nav class="section-nav" aria-label="On this page"><div class="section-pills">{"".join(pills)}</div></nav>'


def _overview(digest: dict) -> str:
    text = (digest.get("brief") or "").strip()
    if text:
        return text
    names = "; ".join(g["name"] for g in digest.get("games", [])[:4])
    return f"This week’s conversation clustered around {names}." if names else "No games met the threshold this week."


def _week_brief(digest: dict) -> str:
    games = digest.get("games", [])
    base = digest.get("baseline_date")
    if base:
        new = sum(1 for g in games if g.get("is_new"))
        up = sum(1 for g in games if (g.get("change_pct") or 0) > 0)
        down = sum(1 for g in games if (g.get("change_pct") or 0) < 0)
        delta = (f'<p class="vs-last">Compared with last publish ({_e(_nice_date(base))}): '
                 f"<span>{new} new</span><span>{up} rising</span><span>{down} falling</span></p>")
    else:
        delta = '<p class="vs-last">First publish in the archive — no prior week to compare.</p>'
    return ('<section class="week-brief" id="week-brief" aria-label="Week in brief"><h2>Week in brief</h2>'
            f'<p class="overview">{_e(_overview(digest))}</p>{delta}</section>')


def _card(g: dict, baseline_date) -> str:
    tags = []
    if g.get("is_new"):
        tags.append('<span class="badge new">New this week</span>')
    elif g.get("change_pct") is not None:
        pct = g["change_pct"]
        cls = "up" if pct > 0 else "down" if pct < 0 else ""
        arrow = "▲" if pct > 0 else "▼" if pct < 0 else "▬"
        tags.append(f'<span class="badge {cls}">{arrow} {abs(pct)}% vs {_e(_short_date(baseline_date))}</span>')
    for p, v in sorted(g["platforms"].items(), key=lambda kv: -kv[1]["engagement"]):
        tags.append(f'<span class="chip {_e(p)}">{_e(config.PLATFORM_LABELS.get(p, p))} · {v["mentions"]}</span>')
    posts = "".join(
        f'<li>{_ICON_REDDIT}<div class="t"><a href="{_e(_safe_url(p["url"]))}" rel="noopener noreferrer">'
        f'{_e(p["title"])}</a><small>r/{_e(p["subreddit"])} · {_compact(p["score"])} up · '
        f'{_compact(p["num_comments"])} comments</small></div></li>'
        for p in g["top_posts"]
    )
    return (
        f'<div class="card game" id="{_e(_slug(g["key"]))}">'
        f'<div class="meta"><span class="rank">#{g["rank"]}</span><span>{_posts(g["mentions"])}</span></div>'
        f'<h3>{_e(g["name"])}</h3><div class="badges">{"".join(tags)}</div>'
        f'<p>{_e(g.get("why", ""))}</p><ul class="top-posts">{posts}</ul>'
        f'<div class="score-row"><span class="score">{g["trending_score"]:.1f}</span>'
        f'<span>trend score · {g["engagement"]:,} upvotes + comments</span></div></div>'
    )


def _threads(games: list, limit: int = 10) -> list:
    """The most engaged threads across the ranked games (each thread once)."""
    seen: dict = {}
    for g in games:
        for p in g["top_posts"]:
            seen.setdefault(p["url"], dict(p, game=g["name"]))
    return sorted(seen.values(), key=lambda p: int(p["score"]) + int(p["num_comments"]), reverse=True)[:limit]


def _threads_section(threads: list) -> str:
    if not threads:
        return ""
    items = "".join(
        f'<li>{_ICON_REDDIT}<div><a href="{_e(_safe_url(t["url"]))}" rel="noopener noreferrer">{_e(t["title"])}</a>'
        f'<small>r/{_e(t["subreddit"])} · {_compact(t["score"])} up · {_compact(t["num_comments"])} '
        f'comments · about {_e(t["game"])}</small></div></li>'
        for t in threads
    )
    return f'<h2 id="top-threads">Top threads</h2><ul class="thread-list">{items}</ul>'


def _platform_section(cols: list) -> str:
    if not cols:
        return ""
    cards = "".join(
        f'<div class="card"><h3>{_e(config.PLATFORM_LABELS[pl])}</h3><ol>'
        + "".join(f'<li>{_e(g["name"])} <small>{_compact(g["platforms"][pl]["engagement"])}</small></li>'
                  for g in ranked)
        + "</ol></div>"
        for pl, ranked in cols
    )
    return ('<h2 id="by-platform">Most discussed by platform</h2>'
            f'<div class="plat-grid">{cards}</div>'
            '<p class="note">Based on platform-specific subreddits only; general subreddits count toward the main ranking.</p>')


def render_page(digest: dict, dates: list, from_archive: bool) -> str:
    date = digest["date"]
    games = digest.get("games", [])
    base = digest.get("baseline_date")
    cols = _platform_cols(games)
    threads = _threads(games)
    cards = "".join(_card(g, base) for g in games) or "<p>No games met the threshold this week.</p>"
    favicon = "../../favicon.svg" if from_archive else "favicon.svg"
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f'<title>Games — Trending This Week · {_e(_nice_date(date))}</title>'
        f'<link rel="icon" href="{favicon}" type="image/svg+xml">{FONTS}<style>{CSS}</style></head><body>'
        '<div class="page"><header class="page-header"><h1>Games — Trending This Week</h1>'
        f'{_section_pills(games, cols, threads)}{_date_nav(date, dates, from_archive)}</header>'
        f'<div class="body-row"><div class="main">{_week_brief(digest)}'
        f'<h2 id="trending-games">Trending games</h2><div class="card-grid">{cards}</div>'
        f'{_platform_section(cols)}{_threads_section(threads)}'
        '<footer>Sourced from public Reddit gaming communities, summarized by a local model. '
        'Reddit measures buzz, not play counts: neither PlayStation nor Xbox publishes player numbers, '
        'and controversy or memes can inflate a game’s score. '
        'Trend score = √(heat) × week-over-week growth boost, where heat adds up each mention '
        'and its upvotes + comments. Game names are extracted from post titles by a small local model '
        'and can be wrong. Links go to the original posts.</footer></div>'
        f'{_timeline(date, dates, from_archive)}</div></div></body></html>'
    )


def render_all() -> None:
    dates = list_dates()
    if not dates:
        raise SystemExit("Nothing to render: no site/archive/*/digest.json yet. Run `python run.py` first.")
    os.makedirs(config.SITE_DIR, exist_ok=True)
    src = os.path.join(os.path.dirname(os.path.abspath(__file__)), "favicon.svg")
    if os.path.isfile(src):
        shutil.copyfile(src, os.path.join(config.SITE_DIR, "favicon.svg"))
    for d in dates:
        with open(os.path.join(config.ARCHIVE_DIR, d, "digest.json")) as f:
            digest = json.load(f)
        with open(os.path.join(config.ARCHIVE_DIR, d, "index.html"), "w") as f:
            f.write(render_page(digest, dates, from_archive=True))
        if d == dates[-1]:
            with open(config.OUTPUT_HTML, "w") as f:
                f.write(render_page(digest, dates, from_archive=False))
    print(f"Rendered {len(dates)} page(s); latest is {config.OUTPUT_HTML} ({dates[-1]})")


def main() -> None:
    render_all()


if __name__ == "__main__":
    main()
