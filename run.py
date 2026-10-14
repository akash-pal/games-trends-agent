"""Run the full pipeline: check Ollama -> fetch -> extract -> score -> analyze -> render.

Usage:
    python run.py                 # everything
    python run.py --check         # only verify Ollama and the model are usable
    python run.py --skip-fetch    # reuse the existing raw_posts.json
    python run.py --date 2026-10-14   # label the snapshot with another date
"""

from __future__ import annotations

import argparse
import datetime
import json
import os

import analyze
import config
import extract
import fetch
import llm
import render
import score


def _write_json(path: str, data: dict) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="only check Ollama, then exit")
    ap.add_argument("--skip-fetch", action="store_true", help="reuse existing raw_posts.json")
    ap.add_argument("--date", help="snapshot date, YYYY-MM-DD (default: today, UTC)")
    args = ap.parse_args(argv)

    run_date = args.date or config.run_date()
    try:
        datetime.datetime.strptime(run_date, "%Y-%m-%d")
    except ValueError:
        raise SystemExit(f"--date must look like 2026-10-14, got '{run_date}'")

    # Fail fast, before spending time on fetching.
    try:
        llm.check()
    except llm.LLMError as e:
        raise SystemExit(str(e))
    if args.check:
        return

    if not args.skip_fetch:
        fetch.main()
    try:
        with open(config.RAW_POSTS_FILE) as f:
            posts = json.load(f)
    except (OSError, ValueError):
        raise SystemExit(f"No usable {config.RAW_POSTS_FILE}. Run without --skip-fetch first.")
    posts.sort(key=lambda p: int(p.get("score") or 0) + int(p.get("num_comments") or 0), reverse=True)
    posts = posts[: config.EXTRACT_TOP_POSTS]

    try:
        post_games = extract.extract_games(posts)
        baseline_date, baseline = score.load_baseline(run_date)
        ranked, heat_index = score.score_games(posts, post_games, baseline)
        top = ranked[: config.TOP_GAMES]
        print(f"Scoring: {len(ranked)} games ranked, showing {len(top)}"
              + (f", comparing with {baseline_date}" if baseline_date else ", no earlier week to compare"))
        print("Writing explanations...")
        analyze.add_reasons(top)
        brief = analyze.make_brief(top, baseline_date)
    except llm.LLMError as e:
        raise SystemExit(str(e))

    digest = {
        "date": run_date,
        "generated_at": datetime.datetime.now(tz=datetime.timezone.utc).isoformat(),
        "model": llm.resolve_model(),
        "baseline_date": baseline_date,
        "posts_analyzed": len(posts),
        "brief": brief,
        "games": top,
        "heat_index": heat_index,
    }
    _write_json(os.path.join(config.ARCHIVE_DIR, run_date, "digest.json"), digest)
    _write_json(config.DIGEST_FILE, digest)
    render.render_all()
    print(f"\nDone. Open {config.OUTPUT_HTML} in your browser.")


if __name__ == "__main__":
    main()
