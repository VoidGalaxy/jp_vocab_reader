from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.dictionary_file_manager import (  # noqa: E402
    ensure_krdict_reverse_file,
    get_krdict_reverse_path,
    get_krdict_reverse_url,
    validate_krdict_reverse_json_file,
)
from app.krdict_reverse_service import (  # noqa: E402
    KRDICT_REVERSE_SAMPLE_PATH,
    get_krdict_reverse_status,
)


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


def check_validator() -> bool:
    """Exercise validate_krdict_reverse_json_file against known-good and
    known-bad structures. Purely local/offline -- no network access."""
    print("Checking krdict reverse JSON validator...")
    all_ok = True

    if KRDICT_REVERSE_SAMPLE_PATH.exists():
        try:
            validate_krdict_reverse_json_file(KRDICT_REVERSE_SAMPLE_PATH)
            print(f"  OK: committed sample passes validation ({KRDICT_REVERSE_SAMPLE_PATH.name})")
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            all_ok = False
            print(f"  FAIL: committed sample should be valid but was rejected: {exc}")
    else:
        print(f"  skipped: {KRDICT_REVERSE_SAMPLE_PATH} not found")

    bad_cases: list[tuple[str, object]] = [
        ("list root instead of object", ["not", "a", "dict"]),
        ("empty object", {}),
        ("non-list value", {"promise": "약속"}),
        ("non-string item in value list", {"promise": [1, 2, 3]}),
    ]
    with tempfile.TemporaryDirectory() as tmp_dir:
        for description, payload in bad_cases:
            tmp_path = Path(tmp_dir) / "bad.json"
            tmp_path.write_text(json.dumps(payload), encoding="utf-8")
            try:
                validate_krdict_reverse_json_file(tmp_path)
                all_ok = False
                print(f"  FAIL: validator accepted invalid input ({description})")
            except (OSError, ValueError, json.JSONDecodeError):
                print(f"  OK: validator correctly rejected invalid input ({description})")

    return all_ok


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Check the krdict reverse index delivery setup: local file state, "
            "KRDIC_REVERSE_URL/KRDIC_REVERSE_PATH configuration, loader status, "
            "and the structural JSON validator. Does not download anything over "
            "the network unless --url is passed explicitly."
        )
    )
    parser.add_argument(
        "--url",
        help="Optional: perform an actual test download from this URL "
        "(temporarily overrides KRDIC_REVERSE_URL for this run only). Not "
        "used by default -- this script does not touch the network otherwise.",
    )
    args = parser.parse_args()

    full_path = get_krdict_reverse_path()
    describe_file(full_path, "full krdict reverse index")
    describe_file(KRDICT_REVERSE_SAMPLE_PATH, "sample krdict reverse index")

    url_configured = bool(get_krdict_reverse_url())
    print()
    print(f"KRDIC_REVERSE_URL configured: {url_configured}")
    print(f"krdict reverse index path: {full_path}")

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

    if status.get("source") != "full":
        print()
        if url_configured:
            print(
                "KRDIC_REVERSE_URL is configured. This script does not download "
                "the file by default; the backend startup path downloads it when "
                "the local full file is missing. Pass --url to test a download "
                "here."
            )
        else:
            print(
                "KRDIC_REVERSE_URL is not configured, so the app uses the small "
                "committed sample. For production, gzip krdict_reverse_full.json "
                "(built with scripts/build_krdict_reverse_index.py), upload it to "
                "file storage, and set KRDIC_REVERSE_URL so the Render backend "
                "can download it at startup."
            )

    print()
    validator_ok = check_validator()

    if args.url:
        print()
        print(f"Testing a real download from --url (length={len(args.url)} chars)...")
        import os

        # Download to a throwaway temp path (never the real configured path)
        # so this test never overwrites/skips based on an existing local
        # full file, and never touches production data.
        previous_url = os.environ.get("KRDIC_REVERSE_URL")
        previous_path = os.environ.get("KRDIC_REVERSE_PATH")
        with tempfile.TemporaryDirectory() as tmp_dir:
            os.environ["KRDIC_REVERSE_URL"] = args.url
            os.environ["KRDIC_REVERSE_PATH"] = str(Path(tmp_dir) / "krdict_reverse_test.json")
            try:
                result = ensure_krdict_reverse_file()
            finally:
                for env_name, previous_value in (
                    ("KRDIC_REVERSE_URL", previous_url),
                    ("KRDIC_REVERSE_PATH", previous_path),
                ):
                    if previous_value is None:
                        os.environ.pop(env_name, None)
                    else:
                        os.environ[env_name] = previous_value
        print(f"  result: {result}")

    if not validator_ok:
        print()
        print("Error: validator check failed.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
