"""Step 1b — Fetch top gaming posts from Reddit.

Strategy per subreddit, first one that returns posts wins:
  0. Reddit OAuth API (only if REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET are set).
  1. Reddit public JSON (top of the week).
  2. Arctic Shift (free archive API).
  3. PullPush (free archive API).
  4. Reddit public Atom RSS (no scores — last resort).

Every post is tagged with the platform of its subreddit (playstation / xbox /
pc / general) and ranked by upvotes + comments. Writes raw_posts.json.
Read-only; never posts or comments.

Fetch strategies adapted from Neha/ai-trends-agent (MIT).
"""

from __future__ import annotations

import base64
import datetime
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

import config

_HEADERS = {
    "User-Agent": config.USER_AGENT,
    "Accept": "application/json, application/atom+xml, */*",
}

_TAG_RE = re.compile(r"<[^>]+>")


def _get(url: str, headers: dict | None = None, timeout: int = 45) -> bytes:
    req = urllib.request.Request(url, headers=headers or _HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _strip_html(text: str) -> str:
    return _TAG_RE.sub("", text or "").strip()


def _week_ago() -> datetime.datetime:
    return datetime.datetime.now(tz=datetime.timezone.utc) - datetime.timedelta(days=7)


def _normalize(item: dict, sub: str) -> dict:
    permalink = item.get("permalink") or ""
    if permalink.startswith("/"):
        url = f"https://reddit.com{permalink}"
    else:
        url = item.get("url") or f"https://reddit.com/r/{sub}"
    created = item.get("created_utc") or time.time()
    return {
        "id": str(item.get("id") or item.get("fullname") or url),
        "subreddit": sub,
        "platform": config.SUBREDDIT_PLATFORMS.get(sub, "general"),
        "source": "reddit",
        "title": item.get("title") or "(no title)",
        "body": (item.get("selftext") or "")[:2000],
        "flair": item.get("link_flair_text") or None,
        "score": int(item.get("score") or 0),
        "num_comments": int(item.get("num_comments") or 0),
        "url": url,
        "created": datetime.datetime.fromtimestamp(
            float(created), tz=datetime.timezone.utc
        ).isoformat(),
    }


def _engagement(post: dict) -> int:
    """Upvotes + comments — primary ranking signal."""
    return int(post.get("score") or 0) + int(post.get("num_comments") or 0)


# ── Strategy 0: official OAuth API ──

_oauth_token: str | None = None


def _get_oauth_token(client_id: str, client_secret: str) -> str:
    global _oauth_token
    if _oauth_token:
        return _oauth_token
    basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    req = urllib.request.Request(
        "https://www.reddit.com/api/v1/access_token",
        data=urllib.parse.urlencode({"grant_type": "client_credentials"}).encode(),
        headers={
            "Authorization": f"Basic {basic}",
            "User-Agent": config.USER_AGENT,
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        _oauth_token = json.loads(resp.read())["access_token"]
    return _oauth_token


def fetch_reddit_oauth(sub: str, limit: int) -> list[dict]:
    creds = config.reddit_credentials()
    if not creds:
        return []  # not configured -> fall through to the next strategy
    token = _get_oauth_token(*creds)
    url = (
        f"https://oauth.reddit.com/r/{sub}/top"
        f"?t={config.TIME_FILTER}&limit={min(limit, 100)}&raw_json=1"
    )
    headers = {"Authorization": f"Bearer {token}", "User-Agent": config.USER_AGENT}
    data = json.loads(_get(url, headers=headers))
    children = data.get("data", {}).get("children", [])
    return [_normalize(c["data"], sub) for c in children if c.get("data")]


# ── Strategies 1-4: public endpoints ──

def fetch_reddit_json(sub: str, limit: int) -> list[dict]:
    url = (
        f"https://www.reddit.com/r/{sub}/top.json"
        f"?t={config.TIME_FILTER}&limit={min(limit, 100)}&raw_json=1"
    )
    data = json.loads(_get(url))
    children = data.get("data", {}).get("children", [])
    return [_normalize(c["data"], sub) for c in children if c.get("data")]


def fetch_arctic_shift(sub: str, limit: int) -> list[dict]:
    """Free Reddit archive API. Pull a wider window, then rank by engagement."""
    params = urllib.parse.urlencode(
        {
            "subreddit": sub,
            "limit": min(max(limit * 2, 80), 100),
            "after": _week_ago().strftime("%Y-%m-%d"),
            "sort": "desc",
        }
    )
    url = f"https://arctic-shift.photon-reddit.com/api/posts/search?{params}"
    data = json.loads(_get(url))
    posts = [_normalize(item, sub) for item in (data.get("data") or [])]
    cutoff = _week_ago().isoformat()
    recent = [p for p in posts if p["created"] >= cutoff] or posts
    recent.sort(key=_engagement, reverse=True)
    return recent[:limit]


def fetch_pullpush(sub: str, limit: int) -> list[dict]:
    params = urllib.parse.urlencode(
        {
            "subreddit": sub,
            "size": min(limit, 100),
            "sort": "desc",
            "sort_type": "score",
            "after": int(_week_ago().timestamp()),
        }
    )
    url = f"https://api.pullpush.io/reddit/search/submission/?{params}"
    data = json.loads(_get(url))
    return [_normalize(item, sub) for item in (data.get("data") or [])]


def fetch_reddit_rss(sub: str, limit: int) -> list[dict]:
    """Public Atom feed. No scores/comment counts, so it ranks last."""
    root = ET.fromstring(_get(f"https://www.reddit.com/r/{sub}/.rss"))
    ns = {"a": "http://www.w3.org/2005/Atom"}
    posts: list[dict] = []
    for entry in root.findall("a:entry", ns)[:limit]:
        title = (entry.findtext("a:title", default="", namespaces=ns) or "").strip()
        link_el = entry.find("a:link", ns)
        link = link_el.get("href") if link_el is not None else ""
        content = entry.findtext("a:content", default="", namespaces=ns) or ""
        updated = entry.findtext("a:updated", default="", namespaces=ns) or ""
        entry_id = entry.findtext("a:id", default="", namespaces=ns) or link
        if not title or not link:
            continue
        try:
            created = datetime.datetime.fromisoformat(updated.replace("Z", "+00:00"))
        except ValueError:
            created = datetime.datetime.now(tz=datetime.timezone.utc)
        posts.append(
            {
                "id": entry_id.split("/")[-1] if "/" in entry_id else entry_id,
                "subreddit": sub,
                "platform": config.SUBREDDIT_PLATFORMS.get(sub, "general"),
                "source": "reddit",
                "title": title,
                "body": _strip_html(content)[:2000],
                "flair": None,
                "score": 0,
                "num_comments": 0,
                "url": link,
                "created": created.isoformat(),
            }
        )
    return posts


def fetch_subreddit(sub: str, limit: int) -> list[dict]:
    strategies = (
        ("Reddit OAuth", fetch_reddit_oauth),
        ("Reddit JSON", fetch_reddit_json),
        ("Arctic Shift", fetch_arctic_shift),
        ("PullPush", fetch_pullpush),
        ("Reddit RSS", fetch_reddit_rss),
    )
    for name, fn in strategies:
        try:
            posts = fn(sub, limit)
            if posts:
                print(f"  r/{sub}: {len(posts)} via {name}")
                return posts
            if name != "Reddit OAuth":  # silent when OAuth simply isn't configured
                print(f"  r/{sub}: {name} empty")
        except Exception as e:
            print(f"  r/{sub}: {name} failed ({e})")
    return []


def fetch_posts() -> list[dict]:
    posts: list[dict] = []
    for sub in config.SUBREDDITS:
        posts.extend(fetch_subreddit(sub, config.POSTS_PER_SUB))
        time.sleep(0.5)  # be polite

    # Dedupe by URL (crossposts), keep the most engaged copy, then rank.
    best: dict[str, dict] = {}
    for p in posts:
        cur = best.get(p["url"])
        if cur is None or _engagement(p) > _engagement(cur):
            best[p["url"]] = p
    unique = sorted(best.values(), key=_engagement, reverse=True)
    return unique


def main() -> None:
    print("Fetching Reddit posts...")
    posts = fetch_posts()
    if not posts:
        # Don't overwrite a previous good file with an empty one, and let
        # fetch.py report this as a failure instead of a silent success.
        raise SystemExit("Reddit: no posts fetched from any source.")
    with open(config.RAW_POSTS_FILE, "w") as f:
        json.dump(posts, f, indent=2)
    print(f"Wrote {len(posts)} posts to {config.RAW_POSTS_FILE}")


if __name__ == "__main__":
    main()
