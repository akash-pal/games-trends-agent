"""Step 1 — Fetch the signals.

Reddit is the only source for now. This module stays as the single entry
point so run.py doesn't change if another source is added later.
"""

import fetch_reddit


def main() -> None:
    fetch_reddit.main()


if __name__ == "__main__":
    main()
