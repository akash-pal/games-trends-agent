"""Step 3 — Turn "which games each post mentions" into a ranked trending list.

For each game:
  heat           = sum over its posts of (1 + ln(1 + upvotes + comments))
                   so every mention counts, and a viral post counts more but
                   with diminishing returns.
  growth boost   = clamp(1 + change vs last run, BOOST_MIN, BOOST_MAX);
                   games absent last run get BOOST_MAX; 1.0 on the first run.
  trending score = sqrt(heat) * boost
                   (sqrt keeps evergreen, always-busy games from drowning out
                   games that are rising fast).

"Last run" is the newest earlier folder in archive/, which stores a heat index
of every game seen. Reddit measures buzz, not play counts.
"""

from __future__ import annotations

import json
import math
import os
import re
from collections import Counter

import config
from extract import norm


def load_baseline(run_date: str):
    """Return (date, {game_key: heat}) from the newest earlier archive, or (None, None)."""
    try:
        names = sorted(
            d for d in os.listdir(config.ARCHIVE_DIR)
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", d) and d < run_date
        )
    except OSError:
        return None, None
    for d in reversed(names):
        try:
            with open(os.path.join(config.ARCHIVE_DIR, d, "digest.json")) as f:
                index = json.load(f).get("heat_index")
        except (OSError, ValueError):
            continue
        if isinstance(index, dict):
            return d, {k: float(v) for k, v in index.items()}
    return None, None


def _engagement(post: dict) -> int:
    return int(post.get("score") or 0) + int(post.get("num_comments") or 0)


def score_games(posts: list, post_games: dict, baseline):
    """Return (ranked games, heat_index for every game seen this run)."""
    agg: dict = {}
    for p in posts:
        eng = _engagement(p)
        for name in post_games.get(p["id"], []):
            key = norm(name)
            if not key:
                continue
            g = agg.setdefault(key, {
                "names": Counter(), "mentions": 0, "engagement": 0,
                "heat": 0.0, "platforms": {}, "posts": [],
            })
            g["names"][name] += 1
            g["mentions"] += 1
            g["engagement"] += eng
            g["heat"] += 1.0 + math.log1p(eng)
            pl = g["platforms"].setdefault(p.get("platform", "general"),
                                           {"mentions": 0, "engagement": 0})
            pl["mentions"] += 1
            pl["engagement"] += eng
            g["posts"].append(p)

    heat_index = {k: round(g["heat"], 3) for k, g in agg.items()}
    ranked = []
    for key, g in agg.items():
        if g["mentions"] < config.MIN_MENTIONS and g["engagement"] < config.MIN_ENGAGEMENT_SINGLE:
            continue
        heat = g["heat"]
        change = None
        is_new = False
        boost = 1.0
        if baseline is not None:
            prev = baseline.get(key)
            if prev is None:
                is_new = True
                boost = config.BOOST_MAX
            else:
                change = (heat - prev) / max(prev, 1.0)
                boost = min(config.BOOST_MAX, max(config.BOOST_MIN, 1.0 + change))
        top_posts = sorted(g["posts"], key=_engagement, reverse=True)[:3]
        ranked.append({
            "key": key,
            "name": g["names"].most_common(1)[0][0],
            "trending_score": round(math.sqrt(heat) * boost, 2),
            "heat": round(heat, 2),
            "boost": round(boost, 2),
            "change_pct": None if change is None else round(change * 100),
            "is_new": is_new,
            "mentions": g["mentions"],
            "engagement": g["engagement"],
            "platforms": g["platforms"],
            "top_posts": [{
                "title": tp["title"], "url": tp["url"], "subreddit": tp["subreddit"],
                "platform": tp.get("platform", "general"),
                "score": tp.get("score", 0), "num_comments": tp.get("num_comments", 0),
            } for tp in top_posts],
        })
    ranked.sort(key=lambda x: (x["trending_score"], x["engagement"]), reverse=True)
    for i, g in enumerate(ranked, 1):
        g["rank"] = i
    return ranked, heat_index
