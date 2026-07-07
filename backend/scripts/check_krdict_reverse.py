from __future__ import annotations

import argparse
import sys
from pathlib import Path


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.krdict_reverse_service import (  # noqa: E402
    KRDICT_REVERSE_FULL_PATH,
    KRDICT_REVERSE_SAMPLE_PATH,
    get_krdict_reverse_status,
    lookup_krdict_reverse,
)


DEFAULT_GLOSSES = [
    "voice",
    "sound",
    "promise",
    "memory",
    "stand up",
    "rise",
    "darkness",
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
        description="Check local krdict reverse index files (English gloss -> Korean words)."
    )
    parser.add_argument("--gloss", action="append", help="Additional gloss to test.")
    args = parser.parse_args()

    describe_file(KRDICT_REVERSE_FULL_PATH, "full krdict reverse index")
    describe_file(KRDICT_REVERSE_SAMPLE_PATH, "sample krdict reverse index")

    status = get_krdict_reverse_status()
    print()
    print(
        "loader status: "
        f"source={status.get('source')} "
        f"entries={status.get('entries')} "
        f"loaded={status.get('loaded')}"
    )
    if status.get("reason"):
        print(f"  reason: {status.get('reason')}")
    for error in status.get("errors", []):
        print(f"  note: {error}")

    print()
    for gloss in [*DEFAULT_GLOSSES, *(args.gloss or [])]:
        print(f"  {gloss}: {', '.join(lookup_krdict_reverse(gloss)) or '-'}")

    if status.get("source") != "full":
        print()
        print(
            "krdict_reverse_full.json is not active; using the small committed "
            "sample. Build a full reverse index with "
            "scripts/build_krdict_reverse_index.py and keep the generated file "
            "out of Git (it is not a translation engine on its own -- it only "
            "boosts/ranks Kaikki-based candidates)."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
