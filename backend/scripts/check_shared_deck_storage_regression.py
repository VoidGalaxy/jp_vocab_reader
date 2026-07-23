"""Storage regression check for shared-deck / JLPT recommended-deck imports.

Guards the core promise of the lexeme-based shared-deck storage model (see
docs/architecture/shared-lexeme-progress-storage.md): importing a
lexeme-mode shared deck must NEVER bulk-copy words into the legacy personal
vocabulary table (`vocab_items`), no matter how large the deck is. Only a
`user_deck_subscriptions` row is created at import time; `user_word_progress`
rows are created lazily, one at a time, only when the user actually acts on a
word (status change / review).

Runs entirely against a throwaway SQLite file (never backend/vocab.db, never
whatever DATABASE_URL is already set in the environment) so it's safe to run
anywhere, including CI, without ever touching a remote/Neon database.

Usage:
    cd backend
    .venv\\Scripts\\Activate.ps1   (or source .venv/bin/activate)
    python scripts/check_shared_deck_storage_regression.py
    python scripts/check_shared_deck_storage_regression.py --count 1000
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Must happen before any `app.*` import touches app.settings/app.database --
# get_database_url() is read at connection time, so setting this first makes
# every get_connection() call in this process target the scratch file, never
# the developer's real backend/vocab.db or a Neon DATABASE_URL that might
# already be set in the environment.
_SCRATCH_DB = Path(tempfile.gettempdir()) / "jp_vocab_reader_storage_regression.db"
_SCRATCH_DB.unlink(missing_ok=True)
os.environ["DATABASE_URL"] = f"sqlite:///{_SCRATCH_DB.as_posix()}"

from app.database import get_connection, init_db, now_iso  # noqa: E402
from app.repositories.lexeme_repository import (  # noqa: E402
    add_word_to_shared_deck,
    is_lexeme_deck,
    update_word_status,
    upsert_lexeme,
)
from app.repositories.shared_deck_repository import import_shared_deck  # noqa: E402

DEFAULT_WORD_COUNT = 200


class RegressionFailure(AssertionError):
    pass


def create_user(email: str, display_name: str) -> int:
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


def create_shared_deck(owner_user_id: int, title: str) -> int:
    timestamp = now_iso()
    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO shared_decks (
                owner_user_id, title, description, visibility,
                vocab_count, custom_term_count, import_count, created_at, updated_at
            )
            VALUES (?, ?, '', 'public', 0, 0, 0, ?, ?)
            """,
            (owner_user_id, title, timestamp, timestamp),
        )
        return int(cursor.lastrowid)


def count_rows(table: str, where: str = "1=1", params: tuple = ()) -> int:
    with get_connection() as connection:
        row = connection.execute(
            f"SELECT COUNT(*) AS c FROM {table} WHERE {where}", params
        ).fetchone()
    return int(row["c"])


def snapshot(importer_id: int) -> dict[str, int]:
    return {
        "vocab_items": count_rows("vocab_items", "user_id = ?", (importer_id,)),
        "lexemes": count_rows("lexemes"),
        "shared_deck_words": count_rows("shared_deck_words"),
        "user_deck_subscriptions": count_rows(
            "user_deck_subscriptions", "user_id = ?", (importer_id,)
        ),
        "user_word_progress": count_rows(
            "user_word_progress", "user_id = ?", (importer_id,)
        ),
    }


def expect_delta(
    label: str, before: dict[str, int], after: dict[str, int], table: str, expected: int
) -> int:
    actual = after[table] - before[table]
    if actual != expected:
        raise RegressionFailure(
            f"{label}: expected `{table}` row count to change by {expected}, "
            f"but it changed by {actual} (before={before[table]}, after={after[table]})"
        )
    return actual


def seed_lexeme_deck(shared_deck_id: int, word_count: int) -> list[int]:
    lexeme_ids: list[int] = []
    for i in range(word_count):
        base_form = f"語彙{i:04d}"
        lexeme_id = upsert_lexeme(
            surface=base_form,
            base_form=base_form,
            reading=f"ごい{i:04d}",
            part_of_speech="명사",
            meaning_ko=f"뜻{i:04d}",
            jlpt_level="N5",
            source_type="jlpt",
        )
        add_word_to_shared_deck(shared_deck_id, lexeme_id, i)
        lexeme_ids.append(lexeme_id)
    with get_connection() as connection:
        connection.execute(
            "UPDATE shared_decks SET vocab_count = ? WHERE id = ?",
            (word_count, shared_deck_id),
        )
    return lexeme_ids


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--count",
        type=int,
        default=DEFAULT_WORD_COUNT,
        help=f"number of test lexemes to seed into the deck (default {DEFAULT_WORD_COUNT}, "
        "must be >= 100)",
    )
    args = parser.parse_args()
    word_count = args.count
    if word_count < 100:
        print(f"--count must be >= 100 (got {word_count})", file=sys.stderr)
        return 1

    print(f"using scratch db: {_SCRATCH_DB}")
    print(f"seeding {word_count} test lexemes into one shared deck")
    init_db()

    try:
        owner_id = create_user("owner@storage-regression.test", "Owner")
        importer_id = create_user("importer@storage-regression.test", "Importer")
        shared_deck_id = create_shared_deck(
            owner_id, "JLPT 추천 어휘 저장량 회귀 테스트 덱"
        )
        lexeme_ids = seed_lexeme_deck(shared_deck_id, word_count)

        if not is_lexeme_deck(shared_deck_id):
            raise RegressionFailure(
                "seeded deck was not detected as lexeme-mode (is_lexeme_deck returned False) "
                "-- shared_deck_words rows may not have been created correctly"
            )

        # --- import ----------------------------------------------------------
        before_import = snapshot(importer_id)
        result = import_shared_deck(importer_id, shared_deck_id)
        if result is None:
            raise RegressionFailure("import_shared_deck returned None for a valid deck id")
        if result.get("mode") != "subscribed":
            raise RegressionFailure(
                f"expected import mode 'subscribed' for a lexeme-mode deck, got {result.get('mode')!r}"
            )
        after_import = snapshot(importer_id)

        vocab_delta_import = expect_delta(
            "after import", before_import, after_import, "vocab_items", 0
        )
        lexemes_delta_import = expect_delta(
            "after import", before_import, after_import, "lexemes", 0
        )
        words_delta_import = expect_delta(
            "after import", before_import, after_import, "shared_deck_words", 0
        )
        subscriptions_delta_import = expect_delta(
            "after import", before_import, after_import, "user_deck_subscriptions", 1
        )
        progress_delta_import = expect_delta(
            "after import", before_import, after_import, "user_word_progress", 0
        )

        # --- re-import must not duplicate the subscription --------------------
        reimport_result = import_shared_deck(importer_id, shared_deck_id)
        if reimport_result is None or reimport_result.get("mode") != "subscribed":
            raise RegressionFailure("re-importing the same deck did not report 'subscribed' mode")
        after_reimport = snapshot(importer_id)
        expect_delta(
            "after re-import",
            after_import,
            after_reimport,
            "user_deck_subscriptions",
            0,
        )

        # --- status change on exactly one word ---------------------------------
        target_lexeme_id = lexeme_ids[0]
        updated = update_word_status(importer_id, target_lexeme_id, "known")
        if updated is None or updated.get("status") != "known":
            raise RegressionFailure("update_word_status did not apply the new status")
        after_status_update = snapshot(importer_id)

        progress_delta_status = expect_delta(
            "after status update",
            after_reimport,
            after_status_update,
            "user_word_progress",
            1,
        )
        vocab_delta_status = expect_delta(
            "after status update",
            after_reimport,
            after_status_update,
            "vocab_items",
            0,
        )

    except RegressionFailure as failure:
        print()
        print("Shared deck storage regression FAILED.")
        print(f"  {failure}")
        return 1

    print()
    print("Shared deck storage regression passed.")
    print(f"vocab_items delta after import: {vocab_delta_import}")
    print(f"lexemes delta after import: {lexemes_delta_import}")
    print(f"shared_deck_words delta after import: {words_delta_import}")
    print(f"subscriptions delta after import: {subscriptions_delta_import}")
    print(f"progress delta after import: {progress_delta_import}")
    print(f"progress delta after status update: {progress_delta_status}")
    print(f"vocab_items delta after status update: {vocab_delta_status}")
    print("re-import duplicate subscriptions: 0 (idempotent)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
