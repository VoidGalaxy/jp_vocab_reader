from __future__ import annotations

import sys
from pathlib import Path


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import build_krdict_reverse_index  # noqa: E402
import fetch_krdict_api  # noqa: E402


BACKEND_DIR = Path(__file__).resolve().parents[1]
DICTIONARY_DIR = BACKEND_DIR / "data" / "dictionary"
SAMPLE_XML_PATH = DICTIONARY_DIR / "krdict_api_response_sample.xml"
SAMPLE_JSON_PATH = DICTIONARY_DIR / "krdict_api_response_sample.json"
CHECK_OUTPUT_PATH = DICTIONARY_DIR / "krdict_raw_fetcher_check.jsonl"


def main() -> int:
    print("This check parses saved sample responses only -- no real krdict API")
    print("call and no API key are needed.")
    print()

    all_entries: list[dict] = []
    for label, path in (("XML sample", SAMPLE_XML_PATH), ("JSON sample", SAMPLE_JSON_PATH)):
        if not path.exists():
            print(f"Error: missing {label} file: {path}", file=sys.stderr)
            return 1
        try:
            entries = fetch_krdict_api.run_from_sample(path)
        except (FileNotFoundError, ValueError) as exc:
            print(f"Error parsing {label} ({path}): {exc}", file=sys.stderr)
            return 1
        print(f"{label}: parsed {len(entries)} entries from {path.name}")
        all_entries.extend(entries)

    if not all_entries:
        print("Error: no entries parsed from sample files.", file=sys.stderr)
        return 1

    fetch_krdict_api.write_entries(CHECK_OUTPUT_PATH, all_entries, mode="w")
    print(f"\nWrote combined check JSONL: {CHECK_OUTPUT_PATH} ({len(all_entries)} entries)")

    try:
        raw_count, skipped_count, index = build_krdict_reverse_index.build_reverse_index(
            CHECK_OUTPUT_PATH
        )
    finally:
        CHECK_OUTPUT_PATH.unlink(missing_ok=True)

    korean_candidates_total = sum(len(values) for values in index.values())
    print()
    print("build_krdict_reverse_index.py compatibility check:")
    print(f"  raw entries processed: {raw_count}")
    print(f"  reverse keys: {len(index)}")
    print(f"  korean candidates total: {korean_candidates_total}")
    print(f"  skipped: {skipped_count}")

    if not index:
        print("Error: fetcher output produced an empty reverse index.", file=sys.stderr)
        return 1

    for key in sorted(index):
        print(f"  {key}: {', '.join(index[key])}")

    print()
    print("OK: krdict API fetcher output is compatible with build_krdict_reverse_index.py.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
