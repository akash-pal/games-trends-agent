"""Step 2 — Find which games each Reddit post is about, using a local model.

Small local models make mistakes, so the model's answer is never trusted
as-is. Every name it returns must:
  * actually appear in the post title (so it can't invent games),
  * not be on config.STOPLIST (PS5, Steam, Sony, ...).
Names in config.ALIASES (BG3, CoD, ...) are also found without the model.

Raw model answers are cached in config.EXTRACT_CACHE_FILE, and the cleaning
above is re-applied on every run, so editing the lists doesn't cost model calls.
"""

from __future__ import annotations

import json
import os
import re

import config
import llm

CACHE_VERSION = 1

SYSTEM_PROMPT = (
    "You identify video game titles in Reddit post titles. "
    "For each numbered post, list the video games it is about or mentions, "
    "using the game's common name.\n"
    "Rules:\n"
    "- Only include names that actually appear in that post's text.\n"
    "- Do not include consoles, platforms, stores, subscriptions, companies or "
    "studios (PS5, Xbox, Steam, Game Pass, Sony, Nintendo...).\n"
    "- Do not include generic words. If no specific game is named, use an empty list.\n"
    'Reply with JSON only, in this shape: {"results":[{"id":1,"games":["Name"]}]}'
)

SCHEMA = {
    "type": "object",
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "games": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["id", "games"],
            },
        }
    },
    "required": ["results"],
}


def norm(text: str) -> str:
    """Lowercase, drop apostrophes, collapse punctuation/whitespace to single spaces."""
    text = (text or "").replace("’", "").replace("'", "").casefold()
    return re.sub(r"[\W_]+", " ", text).strip()


_STOP = {norm(s) for s in config.STOPLIST}
_ALIASES = {norm(k): v for k, v in config.ALIASES.items()}
_ALIASES_BY_CANON: dict = {}
for _alias, _canon in _ALIASES.items():
    _ALIASES_BY_CANON.setdefault(norm(_canon), []).append(_alias)


def _contains(text_norm: str, needle_norm: str) -> bool:
    return bool(needle_norm) and (" " + needle_norm + " ") in (" " + text_norm + " ")


def clean_names(raw_names: list, title: str) -> list:
    """Apply aliases, the stoplist and the 'must appear in the title' check."""
    t = norm(title)
    out: list = []
    seen: set = set()

    def add(name: str) -> None:
        k = norm(name)
        if k and k not in seen:
            seen.add(k)
            out.append(name.strip())

    for alias, canon in _ALIASES.items():
        if _contains(t, alias):
            add(canon)

    for raw in raw_names:
        if not isinstance(raw, str):
            continue
        name = raw.strip()
        n = norm(name)
        if len(n) < 2 or len(name) > 60 or n.isdigit() or n in _STOP:
            continue
        canon = _ALIASES.get(n)
        if canon:  # the model returned an alias such as "bg3"
            name, n = canon, norm(canon)
        grounded = _contains(t, n) or any(
            _contains(t, a) for a in _ALIASES_BY_CANON.get(n, [])
        )
        if grounded:
            add(name)
    return out


def _one_line(text: str, limit: int = 200) -> str:
    return " ".join((text or "").split())[:limit]


def _extract_batch(batch: list) -> dict:
    """Ask the model about one batch. Returns {post_id: [raw names]} for answered posts."""
    lines = [f"{i}. {_one_line(p['title'])}" for i, p in enumerate(batch, 1)]
    data = llm.chat_json(SYSTEM_PROMPT, "\n".join(lines), SCHEMA)
    answers: dict = {}
    for item in data.get("results") or []:
        if not isinstance(item, dict):
            continue
        try:
            idx = int(item.get("id"))
        except (TypeError, ValueError):
            continue
        games = item.get("games")
        if 1 <= idx <= len(batch) and isinstance(games, list):
            answers[batch[idx - 1]["id"]] = [g for g in games if isinstance(g, str)]
    if not answers:
        raise llm.LLMError("model answered, but none of it matched the posts sent")
    return answers  # posts the model skipped are left out, so they're retried next run


def _load_cache(model: str) -> dict:
    try:
        with open(config.EXTRACT_CACHE_FILE) as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    if data.get("version") != CACHE_VERSION or data.get("model") != model:
        return {}
    posts = data.get("posts")
    return posts if isinstance(posts, dict) else {}


def _save_cache(model: str, posts: dict) -> None:
    tmp = config.EXTRACT_CACHE_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump({"version": CACHE_VERSION, "model": model, "posts": posts}, f)
    os.replace(tmp, config.EXTRACT_CACHE_FILE)


def extract_games(posts: list) -> dict:
    """Return {post_id: [game names]} for every post passed in."""
    model = llm.resolve_model()
    cache = _load_cache(model)
    todo = [p for p in posts if p["id"] not in cache]
    size = config.EXTRACT_BATCH_SIZE
    batches = [todo[i : i + size] for i in range(0, len(todo), size)]
    print(f"Extracting games: {len(posts)} posts, {len(posts) - len(todo)} cached, "
          f"{len(batches)} model calls")

    failures = 0
    for n, batch in enumerate(batches, 1):
        print(f"  batch {n}/{len(batches)}")
        try:
            cache.update(_extract_batch(batch))
            failures = 0
        except llm.LLMError as e:
            failures += 1
            print(f"    skipped: {e}")
            if failures >= 3:
                raise SystemExit(
                    "Stopping: 3 batches in a row failed. Progress so far is cached; "
                    "fix the problem above and rerun."
                )
            continue
        _save_cache(model, cache)

    current = {p["id"] for p in posts}
    _save_cache(model, {k: v for k, v in cache.items() if k in current})
    return {p["id"]: clean_names(cache.get(p["id"], []), p["title"]) for p in posts}
