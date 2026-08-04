"""Run the read-only post-deploy shared-deck health checks.

This is an operator convenience wrapper around the two smaller checks:

1. `check_jlpt_package_safety.py` verifies the committed local JLPT package
   JSON files.
2. `check_production_shared_decks.py` calls one anonymous
   `GET /shared-decks` request against the supplied backend base URL.

It never reads `.env`, never touches Neon SQL directly, and never calls a
write endpoint. The backend base URL is intentionally a required CLI argument
so real production URLs are not hardcoded or committed.

Usage:
    cd backend
    .venv\\Scripts\\Activate.ps1   (or source .venv/bin/activate)
    python scripts/run_shared_deck_health_checks.py https://<render-backend>
    python scripts/run_shared_deck_health_checks.py https://<render-backend> --timeout 20
"""

from __future__ import annotations

import argparse
import sys

import check_jlpt_package_safety
import check_production_shared_decks

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "base_url",
        help="Backend base URL, e.g. https://your-backend.onrender.com.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=15.0,
        help="Production HTTP request timeout in seconds (default: 15).",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)

    print("shared-deck post-deploy health checks (read-only)")
    print()

    print("== 1/2 local JLPT package safety ==")
    package_result = check_jlpt_package_safety.main()
    if package_result != 0:
        print()
        print("stopping before the production read-only check because local package safety failed.")
        return package_result

    print()
    print("== 2/2 production shared-deck public list ==")
    production_result = check_production_shared_decks.main(
        [args.base_url, "--timeout", str(args.timeout)]
    )
    if production_result != 0:
        return production_result

    print()
    print("all shared-deck health checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
