"""Storage/behavior regression check for Phase 4: lexeme review logs (see
docs/architecture/shared-lexeme-progress-storage.md).

Guards that logging a subscribed shared-deck/JLPT word's review history to
the new, additive `lexeme_review_logs` table did NOT change any of the
storage promises earlier phases already fixed, and that the log itself is
only ever written on an actual rating submission:

    1. Publish + import still costs 0 vocab_items rows for the importer,
       exactly as check_shared_deck_publish_storage_regression.py already
       checks.
    2. Listing the study queue creates 0 user_word_progress rows AND 0
       lexeme_review_logs rows -- neither table is touched by a read.
    3. One rating on one lexeme item creates exactly 1 user_word_progress
       row (lazy create) AND exactly 1 lexeme_review_logs row.
    4. Rating that same item again does NOT create a second
       user_word_progress row (updated in place) but DOES append a second
       lexeme_review_logs row (one row per rating event, not per word).
    5. vocab_items never grows at any point in this flow.
    6. The existing vocab_items review_logs flow (record_review) is
       completely unaffected -- rating a personal vocab item still logs to
       the original review_logs table, not lexeme_review_logs.

Runs entirely against a throwaway SQLite file (never backend/vocab.db, never
whatever DATABASE_URL is already set in the environment) so it's safe to run
anywhere, including CI, without ever touching a remote/Neon database.

Usage:
    cd backend
    .venv\\Scripts\\Activate.ps1   (or source .venv/bin/activate)
    python scripts/check_lexeme_review_logs_regression.py
    python scripts/check_lexeme_review_logs_regression.py --count 1000
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

# Must happen before any `app.*` import -- see
# check_shared_deck_storage_regression.py for the same pattern/rationale.
_SCRATCH_DB = Path(tempfile.gettempdir()) / "jp_vocab_reader_lexeme_review_logs_regression.db"
_SCRATCH_DB.unlink(missing_ok=True)
os.environ["DATABASE_URL"] = f"sqlite:///{_SCRATCH_DB.as_posix()}"

from app.database import get_connection, init_db, now_iso  # noqa: E402
from app.repositories.lexeme_repository import (  # noqa: E402
    add_word_to_shared_deck,
    list_subscribed_lexeme_study_items,
    record_lexeme_review,
    upsert_lexeme,
)
from app.repositories.shared_deck_repository import import_shared_deck  # noqa: E402
from app.repositories.vocab_repository import (  # noqa: E402
    create_or_update_vocab_item,
    record_review,
)
from app.schemas import VocabItemCreate  # noqa: E402

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


def seed_lexeme_deck(shared_deck_id: int, word_count: int) -> list[int]:
    lexeme_ids: list[int] = []
    for i in range(word_count):
        base_form = f"기록{i:04d}"
        lexeme_id = upsert_lexeme(
            surface=base_form,
            base_form=base_form,
            reading=f"きろく{i:04d}",
            part_of_speech="명사",
            meaning_ko=f"기록뜻{i:04d}",
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


def count_rows(table: str, where: str = "1=1", params: tuple = ()) -> int:
    with get_connection() as connection:
        row = connection.execute(
            f"SELECT COUNT(*) AS c FROM {table} WHERE {where}", params
        ).fetchone()
    return int(row["c"])


def snapshot(user_id: int) -> dict[str, int]:
    return {
        "vocab_items": count_rows("vocab_items", "user_id = ?", (user_id,)),
        "user_word_progress": count_rows(
            "user_word_progress", "user_id = ?", (user_id,)
        ),
        "lexeme_review_logs": count_rows(
            "lexeme_review_logs", "user_id = ?", (user_id,)
        ),
        "review_logs": count_rows("review_logs", "user_id = ?", (user_id,)),
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--count",
        type=int,
        default=DEFAULT_WORD_COUNT,
        help=f"number of test vocab_items/lexemes to seed (default {DEFAULT_WORD_COUNT}, "
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
        publisher_id = create_user("logs-publisher@lexeme-log-regression.test", "LogsPublisher")
        importer_id = create_user("logs-importer@lexeme-log-regression.test", "LogsImporter")

        shared_deck_id = create_shared_deck(publisher_id, "리뷰 로그 회귀 테스트 덱")
        lexeme_ids = seed_lexeme_deck(shared_deck_id, word_count)

        # --- import: 0 vocab_items for importer ------------------------------
        before_import = snapshot(importer_id)
        imported = import_shared_deck(importer_id, shared_deck_id)
        if imported is None or imported.get("mode") != "subscribed":
            raise RegressionFailure("import_shared_deck did not report 'subscribed' mode")
        after_import = snapshot(importer_id)
        expect_delta("after import", before_import, after_import, "vocab_items", 0)
        expect_delta(
            "after import", before_import, after_import, "lexeme_review_logs", 0
        )

        # --- listing the study queue: 0 progress rows, 0 log rows -----------
        queue = list_subscribed_lexeme_study_items(importer_id)
        if len(queue) != word_count:
            raise RegressionFailure(
                f"expected {word_count} items in the study queue, got {len(queue)}"
            )
        after_listing = snapshot(importer_id)
        expect_delta(
            "after listing study queue",
            after_import,
            after_listing,
            "user_word_progress",
            0,
        )
        expect_delta(
            "after listing study queue",
            after_import,
            after_listing,
            "lexeme_review_logs",
            0,
        )

        # --- first rating: +1 progress row, +1 log row -----------------------
        target_lexeme_id = lexeme_ids[0]
        reviewed = record_lexeme_review(
            importer_id, target_lexeme_id, "good", shared_deck_id=shared_deck_id
        )
        if reviewed is None:
            raise RegressionFailure("record_lexeme_review returned None on first rating")
        after_first_rating = snapshot(importer_id)
        progress_delta_first = expect_delta(
            "after first rating",
            after_listing,
            after_first_rating,
            "user_word_progress",
            1,
        )
        logs_delta_first = expect_delta(
            "after first rating",
            after_listing,
            after_first_rating,
            "lexeme_review_logs",
            1,
        )
        expect_delta(
            "after first rating", after_listing, after_first_rating, "vocab_items", 0
        )

        with get_connection() as connection:
            first_log_row = connection.execute(
                """
                SELECT user_id, lexeme_id, shared_deck_id, rating,
                       previous_review_level, new_review_level,
                       previous_status, new_status
                FROM lexeme_review_logs
                WHERE user_id = ? AND lexeme_id = ?
                ORDER BY id DESC LIMIT 1
                """,
                (importer_id, target_lexeme_id),
            ).fetchone()
        if first_log_row is None:
            raise RegressionFailure("no lexeme_review_logs row found after first rating")
        if first_log_row["shared_deck_id"] != shared_deck_id:
            raise RegressionFailure(
                f"expected logged shared_deck_id={shared_deck_id}, got "
                f"{first_log_row['shared_deck_id']}"
            )
        if first_log_row["previous_review_level"] != 0:
            raise RegressionFailure(
                "expected previous_review_level=0 for a never-reviewed word, got "
                f"{first_log_row['previous_review_level']}"
            )
        if first_log_row["new_review_level"] <= first_log_row["previous_review_level"]:
            raise RegressionFailure(
                "expected new_review_level to advance past previous_review_level"
            )

        # --- second rating on the SAME item: 0 more progress rows, +1 log ----
        reviewed_again = record_lexeme_review(
            importer_id, target_lexeme_id, "good", shared_deck_id=shared_deck_id
        )
        if reviewed_again is None:
            raise RegressionFailure("record_lexeme_review returned None on second rating")
        after_second_rating = snapshot(importer_id)
        progress_delta_second = expect_delta(
            "after second rating on the same item",
            after_first_rating,
            after_second_rating,
            "user_word_progress",
            0,
        )
        logs_delta_second_call = expect_delta(
            "after second rating on the same item",
            after_first_rating,
            after_second_rating,
            "lexeme_review_logs",
            1,
        )
        expect_delta(
            "after second rating on the same item",
            after_first_rating,
            after_second_rating,
            "vocab_items",
            0,
        )
        total_logs_after_two_ratings = after_second_rating["lexeme_review_logs"] - after_listing[
            "lexeme_review_logs"
        ]
        if total_logs_after_two_ratings != 2:
            raise RegressionFailure(
                f"expected 2 total lexeme_review_logs rows after 2 ratings, got "
                f"{total_logs_after_two_ratings}"
            )

        # --- lexeme rating without a shared_deck_id must still log ------------
        no_deck_lexeme_id = lexeme_ids[1]
        no_deck_result = record_lexeme_review(importer_id, no_deck_lexeme_id, "hard")
        if no_deck_result is None:
            raise RegressionFailure(
                "record_lexeme_review without shared_deck_id returned None"
            )
        no_deck_log_count = count_rows(
            "lexeme_review_logs",
            "user_id = ? AND lexeme_id = ? AND shared_deck_id IS NULL",
            (importer_id, no_deck_lexeme_id),
        )
        if no_deck_log_count != 1:
            raise RegressionFailure(
                "expected a rating with no shared_deck_id to still log with a NULL "
                f"shared_deck_id, got {no_deck_log_count} matching row(s)"
            )

        # --- the existing personal vocab_items review flow is unaffected ------
        created_item, _was_created = create_or_update_vocab_item(
            importer_id,
            VocabItemCreate(
                surface="복습", base_form="복습", reading="ふくしゅう", meaning_ko="복습"
            ),
        )
        review_logs_before_vocab_review = count_rows(
            "review_logs", "user_id = ?", (importer_id,)
        )
        lexeme_logs_before_vocab_review = count_rows(
            "lexeme_review_logs", "user_id = ?", (importer_id,)
        )
        updated_vocab_item = record_review(importer_id, created_item["id"], "good")
        if updated_vocab_item is None:
            raise RegressionFailure("record_review (vocab) returned None")
        review_logs_after_vocab_review = count_rows(
            "review_logs", "user_id = ?", (importer_id,)
        )
        lexeme_logs_after_vocab_review = count_rows(
            "lexeme_review_logs", "user_id = ?", (importer_id,)
        )
        if review_logs_after_vocab_review - review_logs_before_vocab_review != 1:
            raise RegressionFailure(
                "expected a personal vocab_items rating to append exactly one "
                "review_logs row, as before this phase"
            )
        if lexeme_logs_after_vocab_review != lexeme_logs_before_vocab_review:
            raise RegressionFailure(
                "a personal vocab_items rating must never write to "
                "lexeme_review_logs"
            )

    except RegressionFailure as failure:
        print()
        print("Lexeme review logs regression FAILED.")
        print(f"  {failure}")
        return 1

    print()
    print("Lexeme review logs regression passed.")
    print(f"progress delta after first rating: {progress_delta_first}")
    print(f"lexeme_review_logs delta after first rating: {logs_delta_first}")
    print(f"progress delta after second rating: {progress_delta_second}")
    print(f"lexeme_review_logs delta after second rating: {total_logs_after_two_ratings}")
    print("vocab_items delta: 0")
    print("rating without shared_deck_id still logs (shared_deck_id = NULL): ok")
    print("existing vocab_items review_logs flow unaffected: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
