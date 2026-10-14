"""Central configuration. Loads secrets from .env and defines tunable settings.

Secrets live in .env (see .env.example). Everything else is a plain constant
here so you can tweak behavior without touching the scripts.

Structure adapted from Neha/ai-trends-agent (MIT).
"""

from __future__ import annotations

import datetime
import os
import urllib.parse

from dotenv import load_dotenv

# Load .env from the project root into environment variables.
load_dotenv()


def optional(name: str) -> str | None:
    """Return an env var, or None if unset / still a placeholder."""
    value = os.environ.get(name)
    if not value or value.startswith("your_"):
        return None
    return value


def reddit_credentials() -> tuple[str, str] | None:
    """Optional Reddit 'script' app credentials. Without them, public endpoints are used."""
    client_id = optional("REDDIT_CLIENT_ID")
    client_secret = optional("REDDIT_CLIENT_SECRET")
    if client_id and client_secret:
        return client_id, client_secret
    return None


def ollama_url() -> str:
    """Base URL of the local Ollama server.

    Honors OLLAMA_HOST (which may be 'host:port', a full URL, or '0.0.0.0:11434'
    as people set it for serving) and defaults to http://127.0.0.1:11434.
    """
    raw = (os.environ.get("OLLAMA_HOST") or "").strip() or "127.0.0.1:11434"
    if "://" not in raw:
        raw = "http://" + raw
    parsed = urllib.parse.urlparse(raw)
    host = parsed.hostname or "127.0.0.1"
    if host == "0.0.0.0":
        host = "127.0.0.1"
    return f"{parsed.scheme or 'http'}://{host}:{parsed.port or 11434}"


def ollama_model() -> str | None:
    """Model name from OLLAMA_MODEL, or None to auto-detect (see llm.resolve_model)."""
    return optional("OLLAMA_MODEL")


def run_date() -> str:
    """Today's date (UTC) as YYYY-MM-DD; used to name the archive snapshot."""
    return datetime.datetime.now(tz=datetime.timezone.utc).date().isoformat()


# ── Tunable settings (edit freely) ──

# Descriptive User-Agent for public HTTP requests (Reddit rejects empty/default UAs).
USER_AGENT = "games-trends-agent/0.1 (weekly digest; educational)"

# ── Reddit ──

# subreddit -> platform tag. Platform-specific subs tell us where the buzz is;
# "general" subs cover all platforms.
SUBREDDIT_PLATFORMS = {
    "PS5": "playstation",
    "playstation": "playstation",
    "xbox": "xbox",
    "XboxSeriesX": "xbox",
    "pcgaming": "pc",
    "Steam": "pc",
    "Games": "general",
    "gaming": "general",
    "GamingLeaksAndRumours": "general",
}
SUBREDDITS = list(SUBREDDIT_PLATFORMS)

# How many top posts to pull per subreddit.
POSTS_PER_SUB = 50

# Reddit sort window for "trending": "day", "week", or "month".
TIME_FILTER = "week"

# ── Local LLM (Ollama) ──

# Seconds to wait for one model response. Local models can be slow on first load.
OLLAMA_TIMEOUT = 300

# Context window requested per call. Our prompts are small; keep it low for speed.
OLLAMA_NUM_CTX = 4096

# ── Game extraction ──

# Titles sent to the model per call. Smaller is more reliable on small models.
EXTRACT_BATCH_SIZE = 10

# Only the most-engaged N posts are sent to the model (keeps runtime bounded).
EXTRACT_TOP_POSTS = 250

# Raw model answers are cached here so reruns (and re-tuning the lists below)
# don't repeat model calls. Safe to delete.
EXTRACT_CACHE_FILE = "extract_cache.json"

# Extra names people use -> the name to count them under. Keys are matched
# case-insensitively and ignoring punctuation. Add your own as you spot them.
ALIASES = {
    "bg3": "Baldur's Gate 3",
    "rdr2": "Red Dead Redemption 2",
    "cod": "Call of Duty",
    "gta 5": "Grand Theft Auto V",
    "gta v": "Grand Theft Auto V",
}

# Things a model tends to return that are not games. Matched like ALIASES.
STOPLIST = [
    "ps5", "ps4", "ps3", "ps plus", "playstation", "playstation 5", "playstation plus",
    "xbox", "xbox one", "xbox series x", "xbox series s", "xbox game pass", "game pass",
    "steam", "steam deck", "pc", "switch", "nintendo switch", "nintendo", "sony",
    "microsoft", "epic games", "epic games store", "reddit", "gaming", "game", "games",
    "dlc", "patch", "update", "remake", "remaster", "sequel", "indie",
]

# ── Scoring ──

# A game needs this many posts, or one post with MIN_ENGAGEMENT_SINGLE
# (upvotes + comments), to be ranked. Filters one-off extraction mistakes.
MIN_MENTIONS = 2
MIN_ENGAGEMENT_SINGLE = 500

# Week-over-week growth multiplies a game's score within this range.
# Flat = 1.0x. Games absent last week get BOOST_MAX. First run has no baseline.
BOOST_MIN = 0.5
BOOST_MAX = 2.5

# How many games appear on the page.
TOP_GAMES = 15

# Platform sections on the page, in order.
PLATFORM_ORDER = ("playstation", "xbox", "pc")
PLATFORM_LABELS = {"playstation": "PlayStation", "xbox": "Xbox", "pc": "PC", "general": "General"}

# ── Files (kept in the project root) ──

RAW_POSTS_FILE = "raw_posts.json"
DIGEST_FILE = "digest.json"
# Everything published lives in site/ (this is the folder Cloudflare Pages serves).
SITE_DIR = "site"
OUTPUT_HTML = "site/index.html"

# Per-run archives. Each run writes site/archive/YYYY-MM-DD/{digest.json,index.html};
# the next run reads the newest earlier one to compute week-over-week change.
ARCHIVE_DIR = "site/archive"
