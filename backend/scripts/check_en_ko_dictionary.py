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
from app.dictionary_file_manager import get_en_ko_dictionary_url  # noqa: E402


DEFAULT_GLOSSES = [
    "laziness",
    "self-awareness",
    "to look up at",
    "hope",
    "darkness",
    "voice",
    "sound",
    "promise",
    "memory",
]


def describe_file(path: Path, label: str) -> None:
    print(f"{label}: {path}")
    if not path.exists():
        print("  missing")
        return

    print(f"  exists: {path.stat().st_size} bytes")
    try:
        with path.open("rb") as input_file:
            header = input_file.read(4)
    except OSError:
        header = b""
    if header[:2] == b"\x1f\x8b":
        print("  warning: file looks like a GZIP archive, not JSON")
    elif header[:2] == b"PK":
        print("  warning: file looks like a ZIP archive, not JSON")


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
        f"entries={status.get('entries')} "
        f"keys={status.get('keys')} "
        f"loaded={status.get('loaded')}"
    )
    if status.get("reason"):
        print(f"  reason: {status.get('reason')}")
    for error in status.get("errors", []):
        print(f"  note: {error}")

    print()
    for gloss in [*DEFAULT_GLOSSES, *(args.gloss or [])]:
        print(f"  {gloss}: {translate_glosses_to_korean(gloss) or '-'}")

    if status.get("source") != "full":
        print()
        print(
            "en_ko_full.json is not active. Build it locally with "
            "scripts/build_en_ko_from_kaikki.py and keep the generated file out of Git."
        )
        if get_en_ko_dictionary_url():
            print(
                "EN_KO_DICTIONARY_URL is configured. This script does not download "
                "the file; the backend startup path downloads it when the local full "
                "dictionary file is missing."
            )
        else:
            print(
                "For production, upload en_ko_full.json (or .gz/.zip) to file storage "
                "and set EN_KO_DICTIONARY_URL so the Render backend can download it "
                "at startup."
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
