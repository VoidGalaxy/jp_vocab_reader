from __future__ import annotations

import argparse
import sys
from pathlib import Path


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.jmdict_service import (  # noqa: E402
    JMDICT_FULL_PATH,
    JMDICT_SAMPLE_PATH,
    build_jmdict_index,
    get_jmdict_status,
    read_jmdict_entries,
)
from app.dictionary_file_manager import get_full_dictionary_url  # noqa: E402


DEFAULT_TEST_WORDS = ["怠惰", "自覚", "見上げる", "立ち上がる", "希望", "闇", "声"]


def check_file(path: Path, label: str) -> tuple[list[object] | None, dict[str, list[str]]]:
    print(f"{label}: {path}")
    entries, error = read_jmdict_entries(path)
    if entries is None:
        if error == "missing":
            print(f"  missing: place the file here if this dictionary should be used.")
        elif "ZIP archive" in error:
            print(
                "  invalid: jmdict_full.json appears to be a ZIP archive; "
                "use unzip/normalizer or zipped download support."
            )
        else:
            print(f"  invalid: {error}")
        return None, {}

    index = build_jmdict_index(entries)
    print(f"  readable entries: {len(entries)}")
    print(f"  lookup keys: {len(index)}")
    if not index:
        print("  warning: no valid lookup entries were built.")
    return entries, index


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check local JMdict dictionary files without printing their contents."
    )
    parser.add_argument(
        "--word",
        action="append",
        dest="words",
        help="Additional lookup word to check. Can be passed multiple times.",
    )
    args = parser.parse_args()

    _full_entries, full_index = check_file(JMDICT_FULL_PATH, "full dictionary")
    print()
    _sample_entries, sample_index = check_file(JMDICT_SAMPLE_PATH, "sample dictionary")

    active_index = full_index or sample_index
    active_label = "full" if full_index else "sample" if sample_index else "none"
    words = [*DEFAULT_TEST_WORDS, *(args.words or [])]

    print()
    print(f"active lookup source: {active_label}")
    status = get_jmdict_status()
    print(
        "loader status: "
        f"source={status.get('source')} "
        f"entries={status.get('entry_count')} "
        f"keys={status.get('key_count')}"
    )
    for word in words:
        glosses = active_index.get(word, [])
        if glosses:
            preview = "; ".join(glosses[:5])
            suffix = " ..." if len(glosses) > 5 else ""
            print(f"  {word}: {preview}{suffix}")
        else:
            print(f"  {word}: no local JMdict match")

    if not full_index:
        print()
        if get_full_dictionary_url():
            print(
                "JMDICT_FULL_JSON_URL is configured. This script does not download "
                "the file; the backend startup path downloads it when the local full "
                "dictionary file is missing."
            )
        else:
            print(
                "For production, set JMDICT_FULL_JSON_URL so the Render backend can "
                "download jmdict_full.json at startup when the local file is missing."
            )
        print(
            "jmdict_full.json is not active. The app will continue with the sample "
            "dictionary or empty fallback, but production-quality coverage requires "
            "placing a normalized full dictionary at backend/data/dictionary/jmdict_full.json."
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
