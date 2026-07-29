"""Smoke test for the JLPT seed script's lexeme-mode path.

This closes one local evidence gap from Phase 8: reading the code showed that
`seed_jlpt_shared_decks.py --apply` registers recommended decks through
lexemes/shared_deck_words, and that importing such decks is subscription-only.
This script exercises that path end to end against a tiny fixture package.

It never touches production/Neon data. It forces a throwaway SQLite
DATABASE_URL before importing app modules and deletes the scratch DB plus
sidecars in a finally block.

Usage:
    cd backend
    .venv\\Scripts\\Activate.ps1
    python scripts/smoke_test_jlpt_seed_lexeme_mode.py
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BACKEND_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

# Must happen before any `app.*` import touches app.settings/app.database.
_SCRATCH_DB = Path(tempfile.gettempdir()) / "jp_vocab_reader_smoke_test_jlpt_seed.db"
_SCRATCH_DB.unlink(missing_ok=True)
_DATABASE_URL = f"sqlite:///{_SCRATCH_DB.as_posix()}"
os.environ["DATABASE_URL"] = _DATABASE_URL

if "neon.tech" in _DATABASE_URL.lower() or not _DATABASE_URL.startswith("sqlite:"):
    raise SystemExit(
        "refusing to run: DATABASE_URL is not a safe local sqlite scratch "
        f"file: {_DATABASE_URL}"
    )

from app.database import get_connection  # noqa: E402
from app.repositories.lexeme_repository import is_lexeme_deck  # noqa: E402
from app.repositories.shared_deck_repository import import_shared_deck  # noqa: E402
from app.repositories.vocab_repository import list_vocab_items  # noqa: E402

import seed_jlpt_shared_decks  # noqa: E402

FAILURES: list[str] = []


def check(label: str, condition: bool) -> None:
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}")
    if not condition:
        FAILURES.append(label)


def create_user(email: str, display_name: str) -> int:
    from app.database import now_iso

    timestamp = now_iso()
    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO users (email, display_name, auth_provider, created_at, updated_at)
            VALUES (?, ?, 'local', ?, ?)
            """,
            (email, display_name, timestamp, timestamp),
        )
        return int(cursor.lastrowid)


def write_fixture_package(tmp_dir: Path) -> Path:
    # The title uses the same documented Korean pattern as the real JLPT deck
    # builder: "JLPT N5 recommended vocabulary". Escapes keep this smoke file
    # ASCII-safe across Windows shells.
    package = {
        "package_type": "deck_package",
        "package_version": 1,
        "deck": {
            "name": "JLPT N5 \ucd94\ucc9c \uc5b4\ud718 (Round 7-9 smoke fixture)",
            "description": "smoke-test-only fixture, not a real JLPT deck",
        },
        "vocab_items": [
            {
                "surface": "\u898b\u308b",
                "base_form": "\u898b\u308b",
                "reading": "\u307f\u308b",
                "part_of_speech": "\u52d5\u8a5e",
                "meaning_ko": "\ubcf4\ub2e4",
            },
            {
                "surface": "\u98df\u3079\u308b",
                "base_form": "\u98df\u3079\u308b",
                "reading": "\u305f\u3079\u308b",
                "part_of_speech": "\u52d5\u8a5e",
                "meaning_ko": "\uba39\ub2e4",
            },
            {
                "surface": "\u672c",
                "base_form": "\u672c",
                "reading": "\u307b\u3093",
                "part_of_speech": "\u540d\u8a5e",
                "meaning_ko": "\ucc45",
            },
        ],
        "custom_terms": [],
    }
    path = tmp_dir / "smoke_jlpt_seed_fixture.json"
    path.write_text(json.dumps(package, ensure_ascii=False), encoding="utf-8")
    return path


def main() -> int:
    print(f"using scratch db: {_SCRATCH_DB}")
    tmp_dir = Path(tempfile.mkdtemp(prefix="jp_vocab_reader_smoke_jlpt_seed_"))

    try:
        fixture_path = write_fixture_package(tmp_dir)

        package = seed_jlpt_shared_decks.load_package(fixture_path)
        exit_code = seed_jlpt_shared_decks.run_apply_lexeme(package)
        check("1. seed script's run_apply_lexeme() exits 0", exit_code == 0)

        with get_connection() as connection:
            deck_row = connection.execute(
                "SELECT id FROM shared_decks WHERE title = ?",
                (package.deck.name,),
            ).fetchone()
        check("2. shared_decks row was created", deck_row is not None)
        shared_deck_id = int(deck_row["id"])

        with get_connection() as connection:
            word_rows = connection.execute(
                "SELECT lexeme_id FROM shared_deck_words WHERE shared_deck_id = ?",
                (shared_deck_id,),
            ).fetchall()
        check(
            "3. shared_deck_words has one row per fixture vocab item",
            len(word_rows) == len(package.vocab_items),
        )

        check(
            "4. is_lexeme_deck(shared_deck_id) is True",
            is_lexeme_deck(shared_deck_id),
        )

        with get_connection() as connection:
            legacy_items = connection.execute(
                "SELECT 1 FROM shared_deck_items WHERE shared_deck_id = ?",
                (shared_deck_id,),
            ).fetchall()
            legacy_terms = connection.execute(
                "SELECT 1 FROM shared_deck_terms WHERE shared_deck_id = ?",
                (shared_deck_id,),
            ).fetchall()
        check("5. no legacy shared_deck_items rows were written", len(legacy_items) == 0)
        check("6. no legacy shared_deck_terms rows were written", len(legacy_terms) == 0)

        subscriber_id = create_user("subscriber@smoke.test", "Subscriber")
        before_vocab_count = len(list_vocab_items(subscriber_id))

        import_result = import_shared_deck(subscriber_id, shared_deck_id)
        check("7. import_shared_deck() returns a result", import_result is not None)
        check(
            "8. import mode is 'subscribed', not 'copied'",
            import_result is not None and import_result.get("mode") == "subscribed",
        )

        with get_connection() as connection:
            subscription_row = connection.execute(
                """
                SELECT 1 FROM user_deck_subscriptions
                WHERE user_id = ? AND shared_deck_id = ? AND is_active = TRUE
                """,
                (subscriber_id, shared_deck_id),
            ).fetchone()
        check("9. a user_deck_subscriptions row was created", subscription_row is not None)

        after_vocab_count = len(list_vocab_items(subscriber_id))
        check(
            "10. subscriber's vocab_items count is unchanged (no bulk copy)",
            after_vocab_count == before_vocab_count,
        )

        with get_connection() as connection:
            decks_rows = connection.execute(
                "SELECT 1 FROM decks WHERE user_id = ?",
                (subscriber_id,),
            ).fetchall()
        check("11. no personal deck was created for the subscriber", len(decks_rows) == 0)

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        for suffix in ("", "-wal", "-shm", "-journal"):
            Path(str(_SCRATCH_DB) + suffix).unlink(missing_ok=True)
        print(f"cleaned up scratch db + sidecars: {_SCRATCH_DB}*")

    if FAILURES:
        print(f"\n{len(FAILURES)} check(s) failed: {FAILURES}")
        return 1
    print("\nall checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
