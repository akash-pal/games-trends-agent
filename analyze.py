"""Step 4 — Short plain-English explanations, written by the local model.

The model only sees the Reddit post titles for each game and is told not to
add facts. If a call fails, a factual fallback sentence is used so the page
still renders.
"""

from __future__ import annotations

import config
import llm

WHY_SYSTEM = (
    "You write one short sentence (at most 25 words) explaining why a video game "
    "is being discussed on Reddit this week, using ONLY the post titles provided. "
    "Do not add facts, dates, features or opinions that are not in the titles. "
    "If the titles do not make the reason clear, say neutrally what people are discussing. "
    'Reply with JSON only: {"why":"..."}'
)
WHY_SCHEMA = {
    "type": "object",
    "properties": {"why": {"type": "string"}},
    "required": ["why"],
}

BRIEF_SYSTEM = (
    "You write a 2-3 sentence summary of this week's video game discussion on Reddit, "
    "based ONLY on the trending list provided. Mention which platforms the buzz is on "
    "where the list shows it. Do not add facts that are not in the list. "
    'Reply with JSON only: {"brief":"..."}'
)
BRIEF_SCHEMA = {
    "type": "object",
    "properties": {"brief": {"type": "string"}},
    "required": ["brief"],
}


def _short(text, limit: int) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _fallback_why(game: dict) -> str:
    top = game["top_posts"][0]["title"] if game["top_posts"] else ""
    return f"Discussed in {game['mentions']} posts; most engaged: “{_short(top, 90)}”"


def add_reasons(games: list) -> None:
    """Set game['why'] for each game, in place."""
    for i, game in enumerate(games, 1):
        print(f"  why {i}/{len(games)}: {game['name']}")
        titles = "\n".join(f"- {_short(p['title'], 200)}" for p in game["top_posts"])
        user = f"Game: {game['name']}\nTop Reddit post titles:\n{titles}"
        try:
            why = llm.chat_json(WHY_SYSTEM, user, WHY_SCHEMA).get("why")
        except llm.LLMError as e:
            print(f"    fallback: {e}")
            why = None
        game["why"] = _short(why, 240) if isinstance(why, str) and why.strip() else _fallback_why(game)


def make_brief(games: list, baseline_date) -> str:
    """Two or three sentences for the top of the page ('' if nothing to summarize)."""
    if not games:
        return ""
    rows = []
    for g in games:
        plats = ", ".join(
            f"{config.PLATFORM_LABELS.get(p, p)} {v['mentions']}"
            for p, v in sorted(g["platforms"].items(), key=lambda kv: -kv[1]["engagement"])
        )
        rows.append(f"{g['rank']}. {g['name']} ({plats}) - {g['why']}")
    user = "Trending games this week:\n" + "\n".join(rows)
    try:
        brief = llm.chat_json(BRIEF_SYSTEM, user, BRIEF_SCHEMA).get("brief")
    except llm.LLMError as e:
        print(f"  brief: skipped ({e})")
        brief = None
    if isinstance(brief, str) and brief.strip():
        return _short(brief, 600)
    names = ", ".join(g["name"] for g in games[:3])
    return f"Most talked about this week on Reddit: {names}."
