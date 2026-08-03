"""Read-only production health check for the JLPT shared-deck transition.

Confirms the live public `GET /shared-decks` response still matches the
Phase 14 production-transition record in docs/beta-release-checklist.md:
the five new lexeme-mode JLPT decks (ids 12-16) are public with the expected
title/mode/vocab_count, and the old legacy copied-mode decks (ids 9/8/7/2/1)
no longer appear in the public list.

This script calls exactly one endpoint -- anonymous `GET {base_url}/shared-
decks`, no `Authorization` header -- and never anything else. It never
writes, never touches Neon SQL directly, and never reads `.env`. It takes
the backend base URL as a CLI argument on purpose: the real production URL
must never be hardcoded or committed here (see the "never write real URLs"
rule in docs/beta-release-checklist.md).

Usage:
    cd backend
    .venv\\Scripts\\Activate.ps1   (or source .venv/bin/activate)
    python scripts/check_production_shared_decks.py https://<render-backend>
    python scripts/check_production_shared_decks.py https://<render-backend> --timeout 20

Exit code 0 means every expected check passed. Exit code 1 means at least
one check failed or the request itself failed -- read the printed report
for which one.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

SHARED_DECKS_PATH = "/shared-decks"

# Recorded in docs/beta-release-checklist.md, Phase 14 production transition.
EXPECTED_NEW_DECKS: dict[int, dict[str, Any]] = {
    12: {"title": "JLPT N1 추천 어휘", "vocab_count": 3475},
    13: {"title": "JLPT N2 추천 어휘", "vocab_count": 1830},
    14: {"title": "JLPT N3 추천 어휘", "vocab_count": 1834},
    15: {"title": "JLPT N4 추천 어휘", "vocab_count": 640},
    16: {"title": "JLPT N5 추천 어휘", "vocab_count": 684},
}
EXPECTED_MODE = "subscribed"
EXPECTED_OLD_IDS = (9, 8, 7, 2, 1)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "base_url",
        help="Backend base URL, e.g. https://your-backend.onrender.com "
        "(read from the CLI argument on purpose -- never hardcode or commit "
        "a real production URL).",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=15.0,
        help="HTTP request timeout in seconds (default: 15).",
    )
    return parser.parse_args(argv)


def fetch_shared_decks(base_url: str, timeout: float) -> list[dict[str, Any]]:
    url = base_url.rstrip("/") + SHARED_DECKS_PATH
    request = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = response.read()
    data = json.loads(payload)
    if not isinstance(data, list):
        raise ValueError(f"expected a JSON list from {url}, got {type(data).__name__}")
    return data


def main(argv: list[str]) -> int:
    args = parse_args(argv)

    print("production shared-deck health check (read-only)")
    print(f"target: {args.base_url.rstrip('/')}{SHARED_DECKS_PATH}")
    print("no Authorization header sent (anonymous/public-list view)")
    print()

    try:
        decks = fetch_shared_decks(args.base_url, args.timeout)
    except urllib.error.HTTPError as exc:
        print(f"[FAIL] request failed: HTTP {exc.code} {exc.reason}")
        return 1
    except (urllib.error.URLError, TimeoutError) as exc:
        print(f"[FAIL] request failed: {exc}")
        return 1
    except (ValueError, json.JSONDecodeError) as exc:
        print(f"[FAIL] unexpected response body: {exc}")
        return 1

    by_id = {int(deck["id"]): deck for deck in decks if "id" in deck}
    failures = 0

    for deck_id, expected in EXPECTED_NEW_DECKS.items():
        deck = by_id.get(deck_id)
        if deck is None:
            print(f"[FAIL] new deck id={deck_id}: not present in public list")
            failures += 1
            continue

        checks = [
            ("title", deck.get("title"), expected["title"]),
            ("mode", deck.get("mode"), EXPECTED_MODE),
            ("is_published", deck.get("is_published"), True),
            ("vocab_count", deck.get("vocab_count"), expected["vocab_count"]),
        ]
        deck_ok = True
        for field, actual, want in checks:
            if actual != want:
                print(
                    f"[FAIL] new deck id={deck_id}: {field}={actual!r}, "
                    f"expected {want!r}"
                )
                deck_ok = False
                failures += 1
        if deck_ok:
            print(
                f"[PASS] new deck id={deck_id}: title={deck['title']!r} "
                f"mode={deck['mode']!r} is_published={deck['is_published']!r} "
                f"vocab_count={deck['vocab_count']!r}"
            )

    for old_id in EXPECTED_OLD_IDS:
        if old_id in by_id:
            print(
                f"[FAIL] legacy deck id={old_id} is still in the public list "
                f"(expected it to stay hidden after the Phase 14 soft-unpublish)"
            )
            failures += 1
        else:
            print(f"[PASS] legacy deck id={old_id} is not in the public list")

    print()
    if failures:
        print(f"{failures} check(s) failed.")
        return 1
    print("all checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
