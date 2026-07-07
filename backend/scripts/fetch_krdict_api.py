from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Iterable


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# Development/preprocessing-only fetcher for the 국립국어원 한국어기초사전/
# 우리말샘 Open API. The running app never imports or calls this script --
# it is a manual, offline tool that writes raw JSONL for
# scripts/build_krdict_reverse_index.py. See docs/dictionary-data.md.

# Resolved from this file's location, not the current working directory, so
# the script finds backend/.env whether it is run from backend/ or
# backend/scripts/.
BACKEND_DIR = Path(__file__).resolve().parents[1]
ENV_FILE_PATH = BACKEND_DIR / ".env"

API_BASE_URL = "https://krdict.korean.go.kr/api/search"
ENV_KEY_NAMES = ("KRDIC_API_KEY", "KRDICT_API_KEY")

DEFAULT_LIMIT = 100
DEFAULT_SLEEP = 0.5
DEFAULT_MAX_RETRIES = 3
DEFAULT_TIMEOUT = 20.0
DEFAULT_SEED_FILE = BACKEND_DIR / "data" / "dictionary" / "krdict_seed_sample.txt"
DEFAULT_OUTPUT = BACKEND_DIR / "data" / "dictionary" / "krdict_raw_real.jsonl"

_env_file_loaded = False


def _parse_env_file_fallback(path: Path) -> dict[str, str]:
    """Minimal KEY=VALUE parser used only if python-dotenv is not installed."""
    values: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError:
        return values
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        if stripped.lower().startswith("export "):
            stripped = stripped[len("export ") :].strip()
        key, _, value = stripped.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key:
            values[key] = value
    return values


def _load_env_file_once() -> None:
    """Load backend/.env into the process environment, on demand only.

    Only called after the process environment has already been checked and
    found to have no usable key, so it is safe to let a value from .env win
    over a stale/empty same-named variable already sitting in os.environ.
    """
    global _env_file_loaded
    if _env_file_loaded:
        return
    _env_file_loaded = True
    if not ENV_FILE_PATH.exists():
        return
    try:
        from dotenv import load_dotenv
    except ImportError:
        for key, value in _parse_env_file_fallback(ENV_FILE_PATH).items():
            if value:
                os.environ[key] = value
        return
    load_dotenv(ENV_FILE_PATH, override=True)


def get_api_key() -> tuple[str, str] | None:
    """Resolve the krdict API key.

    Order: current process environment (KRDIC_API_KEY, then
    KRDICT_API_KEY) first, so an explicit shell/platform environment
    variable always wins; only if neither is set does this fall back to
    loading backend/.env and checking both names again.
    """
    for name in ENV_KEY_NAMES:
        value = os.environ.get(name)
        if value and value.strip():
            return value.strip(), "process environment"

    _load_env_file_once()

    for name in ENV_KEY_NAMES:
        value = os.environ.get(name)
        if value and value.strip():
            return value.strip(), str(ENV_FILE_PATH)

    return None


def load_seed_words(path: Path) -> list[str]:
    if not path.exists():
        raise FileNotFoundError(f"seed file not found: {path}")
    words: list[str] = []
    seen: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        word = line.strip()
        if not word or word.startswith("#"):
            continue
        if word not in seen:
            seen.add(word)
            words.append(word)
    return words


def load_done_words(output_path: Path) -> set[str]:
    done: set[str] = set()
    if not output_path.exists():
        return done
    with output_path.open("r", encoding="utf-8") as input_file:
        for line in input_file:
            text = line.strip()
            if not text:
                continue
            try:
                entry = json.loads(text)
            except json.JSONDecodeError:
                continue
            word = entry.get("word") if isinstance(entry, dict) else None
            if isinstance(word, str) and word.strip():
                done.add(word.strip())
    return done


def sniff_format(text: str) -> str:
    return "xml" if text.lstrip().startswith("<") else "json"


def _split_translation_word(word: str) -> list[str]:
    # The real API often returns several English glosses joined in one
    # field, e.g. "promise; appointment; pledge" -- split so each becomes
    # its own reverse-index lookup key instead of one unmatchable phrase.
    return [part.strip() for part in word.split(";") if part.strip()]


def parse_translation_items(raw_items: Any) -> list[dict[str, str]]:
    if raw_items is None:
        return []
    if not isinstance(raw_items, list):
        raw_items = [raw_items]

    translations: list[dict[str, str]] = []
    for item in raw_items:
        if isinstance(item, str):
            for part in _split_translation_word(item):
                translations.append({"language": "", "word": part})
        elif isinstance(item, dict):
            word = item.get("trans_word") or item.get("word") or item.get("trans")
            language = item.get("trans_lang") or item.get("language") or item.get("lang")
            if isinstance(word, str) and word.strip():
                language_value = str(language or "").strip()
                for part in _split_translation_word(word):
                    translations.append({"language": language_value, "word": part})
    return translations


def parse_json_items(data: Any) -> list[dict[str, Any]]:
    items: Any = None
    if isinstance(data, dict):
        channel = data.get("channel")
        if isinstance(channel, dict):
            items = channel.get("item")
        if items is None:
            items = data.get("item") or data.get("items") or data.get("results")
    elif isinstance(data, list):
        items = data

    if items is None:
        return []
    if isinstance(items, dict):
        items = [items]
    if not isinstance(items, list):
        return []

    entries: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        word = item.get("word") or item.get("headword")
        if not isinstance(word, str) or not word.strip():
            continue

        sense_list = item.get("sense") or item.get("senses")
        senses: list[dict[str, Any]] = []
        if isinstance(sense_list, list):
            for sense in sense_list:
                if not isinstance(sense, dict):
                    continue
                definition = sense.get("definition") or sense.get("dfn") or ""
                translations = parse_translation_items(
                    sense.get("translation") or sense.get("translations")
                )
                if translations:
                    senses.append({"definition": str(definition).strip(), "translation": translations})

        if senses:
            entries.append({"word": word.strip(), "sense": senses, "source": "krdict_api"})
    return entries


def parse_xml_items(text: str) -> list[dict[str, Any]]:
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise ValueError(f"invalid XML response: {exc}") from exc

    entries: list[dict[str, Any]] = []
    for item_elem in root.iter("item"):
        word = item_elem.findtext("word")
        if not word or not word.strip():
            continue

        senses: list[dict[str, Any]] = []
        for sense_elem in item_elem.findall("sense"):
            definition = sense_elem.findtext("definition") or sense_elem.findtext("dfn") or ""
            translations: list[dict[str, str]] = []
            for trans_elem in sense_elem.findall("translation"):
                trans_word = (
                    trans_elem.findtext("trans_word")
                    or trans_elem.findtext("word")
                    or trans_elem.findtext("trans")
                )
                language = trans_elem.findtext("trans_lang") or trans_elem.findtext("language")
                if trans_word and trans_word.strip():
                    language_value = (language or "").strip()
                    for part in _split_translation_word(trans_word):
                        translations.append({"language": language_value, "word": part})
            if translations:
                senses.append({"definition": definition.strip(), "translation": translations})

        if senses:
            entries.append({"word": word.strip(), "sense": senses, "source": "krdict_api"})
    return entries


def parse_response_text(text: str) -> list[dict[str, Any]]:
    if sniff_format(text) == "xml":
        return parse_xml_items(text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"response is neither valid XML nor valid JSON: {exc}") from exc
    return parse_json_items(data)


def build_request_url(word: str, api_key: str) -> str:
    params = {
        "key": api_key,
        "q": word,
        "req_type": "json",
        "translated": "y",
        "trans_lang": "1",
        "part": "word",
        "method": "exact",
    }
    return f"{API_BASE_URL}?{urllib.parse.urlencode(params)}"


def fetch_word(word: str, api_key: str, timeout: float, max_retries: int) -> list[dict[str, Any]]:
    url = build_request_url(word, api_key)
    last_error: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            request = urllib.request.Request(
                url, headers={"User-Agent": "jp-vocab-reader-krdict-fetcher/1.0"}
            )
            with urllib.request.urlopen(request, timeout=timeout) as response:
                text = response.read().decode("utf-8", errors="replace")
            return parse_response_text(text)
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            last_error = exc
            print(f"  warning: attempt {attempt}/{max_retries} failed for '{word}': {exc}")
            if attempt < max_retries:
                time.sleep(min(2**attempt, 10))
    print(f"  error: giving up on '{word}' after {max_retries} attempts ({last_error})")
    return []


def run_from_sample(sample_path: Path) -> list[dict[str, Any]]:
    if not sample_path.exists():
        raise FileNotFoundError(f"sample response file not found: {sample_path}")
    text = sample_path.read_text(encoding="utf-8")
    return parse_response_text(text)


def write_entries(output_path: Path, entries: Iterable[dict[str, Any]], mode: str) -> int:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with output_path.open(mode, encoding="utf-8") as output_file:
        for entry in entries:
            output_file.write(json.dumps(entry, ensure_ascii=False) + "\n")
            count += 1
    return count


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Fetch a small batch of 국립국어원 한국어기초사전/우리말샘 entries "
            "from the real Open API (or replay a saved sample response) and "
            "save them as raw JSONL for scripts/build_krdict_reverse_index.py. "
            "Development/preprocessing tool only -- the running app never "
            "calls this API."
        )
    )
    parser.add_argument(
        "--seed-file",
        default=str(DEFAULT_SEED_FILE),
        help="Text file, one Korean word per line (default: %(default)s).",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT),
        help="Output JSONL path (default: %(default)s).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
        help="Max number of seed words to fetch this run (default: %(default)s). "
        "Large batches must be requested explicitly with a bigger --limit.",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=DEFAULT_SLEEP,
        help="Seconds to sleep between API requests (default: %(default)s).",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=DEFAULT_MAX_RETRIES,
        help="Retries per word on failure (default: %(default)s).",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT,
        help="Per-request timeout in seconds (default: %(default)s).",
    )
    parser.add_argument(
        "--resume",
        dest="resume",
        action="store_true",
        default=True,
        help="Skip words already present in --output (default: on).",
    )
    parser.add_argument(
        "--no-resume",
        dest="resume",
        action="store_false",
        help="Disable resume matching; combine with --overwrite to start clean.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Truncate --output before writing instead of resuming/appending.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch/parse but do not write to --output; print counts only.",
    )
    parser.add_argument(
        "--input-sample",
        help="Parse a saved sample API response (XML or JSON) instead of calling "
        "the real API. No API key or network access needed.",
    )
    args = parser.parse_args()

    output_path = Path(args.output)

    if args.input_sample:
        sample_path = Path(args.input_sample)
        print(f"Offline mode: parsing sample response from {sample_path}")
        try:
            entries = run_from_sample(sample_path)
        except (FileNotFoundError, ValueError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        print(f"Parsed {len(entries)} entries from sample response.")
        if args.dry_run:
            print("Dry run: not writing output.")
            return 0
        mode = "w" if args.overwrite else "a"
        written = write_entries(output_path, entries, mode)
        print(f"Wrote {written} entries to {output_path}")
        print("Reminder: raw JSONL fetch output is intentionally ignored by Git.")
        return 0

    key_result = get_api_key()
    if not key_result:
        print(
            "Error: no krdict API key found. Checked the KRDIC_API_KEY and "
            "KRDICT_API_KEY environment variables, then "
            f"{ENV_FILE_PATH} (only used as a fallback if either is not set "
            "in the process environment). For local development, add "
            f"KRDIC_API_KEY=... to {ENV_FILE_PATH} (never commit that file). "
            "For CI/Render/other platforms, inject KRDIC_API_KEY as a "
            "platform environment variable instead. Setting $env:KRDIC_API_KEY "
            "directly in a shell is fine for a one-off test but is not the "
            "supported way to run this regularly. Request an API key at "
            "https://krdict.korean.go.kr (한국어기초사전) or "
            "https://opendict.korean.go.kr (우리말샘) -- see "
            "docs/dictionary-data.md. To try this script without a key, use "
            "--input-sample with a saved sample response instead.",
            file=sys.stderr,
        )
        return 1
    api_key, key_source = key_result
    print(f"krdict API key: found (source={key_source}, length={len(api_key)})")

    if args.limit <= 0:
        print("Error: --limit must be a positive integer.", file=sys.stderr)
        return 1

    try:
        seed_words = load_seed_words(Path(args.seed_file))
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    done_words: set[str] = set()
    if args.resume and not args.overwrite:
        done_words = load_done_words(output_path)
        if done_words:
            print(f"Resume: {len(done_words)} word(s) already in {output_path}, will be skipped.")

    pending_words = [word for word in seed_words if word not in done_words][: args.limit]
    print(
        f"Seed words: {len(seed_words)} total, {len(pending_words)} to fetch "
        f"this run (limit={args.limit})."
    )

    if args.dry_run:
        print("Dry run: not calling the API or writing output.")
        for word in pending_words:
            print(f"  would fetch: {word}")
        return 0

    if not pending_words:
        print("Nothing to do (all seed words already fetched, or seed file is empty).")
        return 0

    mode = "w" if args.overwrite else "a"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fetched_count = 0
    entry_count = 0
    with output_path.open(mode, encoding="utf-8") as output_file:
        for index, word in enumerate(pending_words, start=1):
            print(f"[{index}/{len(pending_words)}] fetching '{word}'...")
            entries = fetch_word(word, api_key, timeout=args.timeout, max_retries=args.max_retries)
            for entry in entries:
                output_file.write(json.dumps(entry, ensure_ascii=False) + "\n")
                entry_count += 1
            output_file.flush()
            fetched_count += 1
            if index < len(pending_words):
                time.sleep(args.sleep)

    print(f"Done. Words fetched: {fetched_count}, entries written: {entry_count}")
    print(f"Output: {output_path}")
    print("Reminder: raw JSONL fetch output is intentionally ignored by Git.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
