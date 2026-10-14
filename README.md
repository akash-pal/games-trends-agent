# Games Trends Agent

A weekly "what are PlayStation, Xbox and PC players talking about" page, built from public Reddit discussion and summarized by a **local Ollama model**. No API keys, no accounts, nothing leaves your machine except the Reddit requests.

Structure and Reddit fetch strategies are adapted from [Neha/ai-trends-agent](https://github.com/Neha/ai-trends-agent) (MIT).

## What the signal is (and isn't)

Reddit measures **buzz**, not play counts. Neither PlayStation nor Xbox publishes player data, so a trending game here is one people are posting and commenting about. Controversies and memes inflate it, it skews English-speaking and Western, and game names come from post titles via a small model, so some will be wrong or missed. The page says this in its footer.

## How it works

```
fetch_reddit.py -> raw_posts.json          top posts of the week from 9 subreddits, tagged playstation / xbox / pc / general
extract.py      -> game names per post     local model reads titles; names must appear in the title, stoplist + aliases applied
score.py        -> ranked games            trend score vs the previous week in archive/
analyze.py      -> one-line "why" + brief  local model, told to use only the post titles
render.py       -> site/index.html + site/archive/   static site with a timeline of past weeks (layout and theme adapted from ai-trends-agent)
```

**Trend score** = √heat × growth boost. *Heat* adds `1 + ln(1 + upvotes + comments)` for every post that mentions the game. The *boost* is `1 + change vs last week`, limited to 0.5×–2.5× (games absent last week get 2.5×; the first run has no comparison, so 1×). The square root stops always-busy games drowning out ones that are rising fast. All the limits are in `config.py`.

## Setup

1. Install [Ollama](https://ollama.com), start it, and pull a model. A 7–8B instruction model is a sensible starting point, for example `ollama pull qwen2.5:7b` or `ollama pull llama3.1:8b` (not benchmarked here; bigger models extract names more reliably, smaller ones run faster).
2. Python 3.9+:

```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python run.py --check     # confirms Ollama is reachable and picks the model
python run.py             # fetch -> extract -> score -> analyze -> render
open site/index.html
```

If you have exactly one model installed it is used automatically. With several, set `OLLAMA_MODEL` in `.env` (copy `.env.example`; `ollama list` shows names). `OLLAMA_HOST` is honored if Ollama isn't on the default port.

The first run takes a while (about 25 model calls for extraction, then one per game). Raw model answers are cached in `extract_cache.json`, so reruns are fast and an interrupted run resumes.

## Commands

```
python run.py                    # everything
python run.py --check            # only verify Ollama and the model
python run.py --skip-fetch       # reuse raw_posts.json (tune prompts/scoring without refetching)
python run.py --date 2026-10-14  # label the snapshot with another date
python render.py                 # re-render pages from archive/ without touching the model
python llm.py                    # same check as --check
```

Run it weekly (the page compares with the newest earlier snapshot in `site/archive/`). Keep `site/archive/` between runs, since that is where last week's numbers live.

## Tuning quality

`config.py` is where to improve results:

- `ALIASES`: names people use for a game, counted under one name (`"bg3": "Baldur's Gate 3"`).
- `STOPLIST`: things the model wrongly returns as games (`"steam deck"`).
- `EXTRACT_BATCH_SIZE`: lower it (e.g. 5) if a small model returns malformed or mismatched answers.
- `MIN_MENTIONS` / `MIN_ENGAGEMENT_SINGLE`: how much evidence a game needs before it is ranked.
- `SUBREDDIT_PLATFORMS`, `POSTS_PER_SUB`, `TIME_FILTER`: where and how much to read.

Editing `ALIASES` or `STOPLIST` takes effect on the next run without new model calls.

## Publish to Cloudflare Pages

Everything public lives in `site/`. Cloudflare serves that folder; the Python source and your `.env` are never part of the site.

1. Create an empty GitHub repo, then from this folder: `git init -b main && git add . && git commit -m "Initial commit" && git remote add origin <repo-url> && git push -u origin main`
2. In Cloudflare: Workers & Pages -> Create -> Pages -> Connect to Git -> pick the repo. Framework preset **None**, build command **empty**, build output directory **site**.
3. Each week: `./publish.sh` runs the pipeline, commits `site/`, and pushes; Cloudflare redeploys within a minute.

## Reddit access

Public endpoints work from a home connection but are often blocked from CI servers. If the fetch fails, it tries Reddit JSON, Arctic Shift, PullPush and RSS in turn, and exits with an error (keeping your previous `raw_posts.json`) if all fail. For reliable scheduled runs, create a *script* app at <https://www.reddit.com/prefs/apps> and set `REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET` in `.env`.

## Files

| Path | Purpose |
| ---- | ------- |
| `site/archive/YYYY-MM-DD/` | one snapshot per run: `digest.json` and `index.html` (keep these) |
| `site/index.html` | latest week (this folder is what you publish) |
| `favicon.svg` | tab icon used by the pages |
| `raw_posts.json`, `extract_cache.json`, `digest.json` | working files, safe to delete |

## License

MIT, see `LICENSE`.
