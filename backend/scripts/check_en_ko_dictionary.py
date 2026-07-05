from __future__ import annotations

import argparse
import sys
from pathlib import Path


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.en_ko_dictionary_service import (  # noqa: E402
    EN_KO_FULL_PATH,
    EN_KO_SAMPLE_PATH,
    get_en_ko_status,
    translate_glosses_to_korean,
)


DEFAULT_GLOSSES = [
    "laziness",
    "self-awareness",
    "to look up at",
    "hope",
    "darkness",
    "voice",
]


def describe_file(path: Path, label: str) -> None:
    print(f"{label}: {path}")
    if path.exists():
        print(f"  exists: {path.stat().st_size} bytes")
    else:
        print("  missing")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check local English-Korean fallback dictionary files."
    )
    parser.add_argument("--gloss", action="append", help="Additional gloss to test.")
    args = parser.parse_args()

    describe_file(EN_KO_FULL_PATH, "full English-Korean dictionary")
    describe_file(EN_KO_SAMPLE_PATH, "sample English-Korean dictionary")

    status = get_en_ko_status()
    print()
    print(
        "loader status: "
        f"source={status.get('source')} "
        f"entries={status.get('entry_count')} "
        f"keys={status.get('key_count')}"
    )
    for error in status.get("errors", []):
        print(f"  note: {error}")

    print()
    for gloss in [*DEFAULT_GLOSSES, *(args.gloss or [])]:
        print(f"  {gloss}: {translate_glosses_to_korean(gloss) or '-'}")

    if status.get("source") != "full":
        print()
        print(
            "en_ko_full.json is not active. Build it with "
            "scripts/build_en_ko_from_kaikki.py and keep the generated file out of Git."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
