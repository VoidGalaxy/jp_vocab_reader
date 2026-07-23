"""Regression check for Phase 6: lexeme SRS status policy (see
docs/architecture/shared-lexeme-progress-storage.md).

Guards the fix for the "unclassified forever" blind spot: before this
phase, rating a lexeme (record_lexeme_review()) advanced review_level but
never touched status, so a rated word stayed status='unclassified' --
dropping out of new_count (review_level > 0) without ever qualifying for
due_count/hard_count (both require status IN ('unknown', 'uncertain')).

Checks, entirely against a throwaway SQLite file (never backend/vocab.db,
never whatever DATABASE_URL is already set in the environment, never a
remote/Neon database):

    A. First rating auto-corrects status (only when it was 'unclassified'):
       again -> unknown, hard -> uncertain, good -> uncertain,
       easy -> known. lexeme_review_logs.previous_status/new_status record
       the correction exactly, and the API-shaped return value's `status`
       reflects the corrected value too.
    B. A status the user already set manually (update_word_status()) is
       NEVER overwritten by a later rating -- previous_status == new_status
       in the log, and the progress row's status is unchanged.
    C. The due/new blind spot is actually fixed: a "good"-rated word whose
       next_review_at is adjusted into the past now counts in
       lexeme_due_count (it didn't before this phase, since its status
       never left 'unclassified'); an "easy"-rated word (status: known)
       never counts as due regardless of next_review_at; rated words drop
       out of lexeme_new_count as before.
    D. No storage/read side effects: import alone, and listing the study
       queue alone, never create user_word_progress/lexeme_review_logs
       rows; only an actual rating does. vocab_items is never touched.

Usage:
    cd backend
    .venv\\Scripts\\Activate.ps1   (or source .venv/bin/activate)
    python scripts/check_lexeme_srs_status_policy_regression.py
    python scripts/check_lexeme_srs_status_policy_regression.py --count 1000
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
_SCRATCH_DB = Path(tempfile.gettempdir()) / "jp_vocab_reader_lexeme_srs_status_policy_regression.db"
_SCRATCH_DB.unlink(missing_ok=True)
os.environ["DATABASE_URL"] = f"sqlite:///{_SCRATCH_DB.as_posix()}"

from app.database import get_connection, init_db, now_iso  # noqa: E402
from app.repositories.lexeme_repository import (  # noqa: E402
    add_word_to_shared_deck,
    list_subscribed_lexeme_study_items,
    record_lexeme_review,
    update_word_status,
    upsert_lexeme,
)
from app.repositories.shared_deck_repository import import_shared_deck  # noqa: E402
from app.repositories.stats_repository import build_stats  # noqa: E402

DEFAULT_WORD_COUNT = 200
RATING_TO_EXPECTED_STATUS = {
    "again": "unknown",
    "hard": "uncertain",
    "good": "uncertain",
    "easy": "known",
}


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
        base_form = f"정책{i:04d}"
        lexeme_id = upsert_lexeme(
            surface=base_form,
            base_form=base_form,
            reading=f"せいさく{i:04d}",
            part_of_speech="명사",
            meaning_ko=f"정책뜻{i:04d}",
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


def expect_equal(label: str, actual, expected) -> None:
    if actual != expected:
        raise RegressionFailure(f"{label}: expected {expected!r}, got {actual!r}")


def get_last_log_row(user_id: int, lexeme_id: int) -> dict:
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT rating, previous_status, new_status, previous_review_level,
                   new_review_level
            FROM lexeme_review_logs
            WHERE user_id = ? AND lexeme_id = ?
            ORDER BY id DESC LIMIT 1
            """,
            (user_id, lexeme_id),
        ).fetchone()
    if row is None:
        raise RegressionFailure(f"no lexeme_review_logs row found for lexeme_id={lexeme_id}")
    return dict(row)


def set_next_review_at_in_past(user_id: int, lexeme_id: int) -> None:
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE user_word_progress
            SET next_review_at = '2000-01-01T00:00:00+00:00'
            WHERE user_id = ? AND lexeme_id = ?
            """,
            (user_id, lexeme_id),
        )


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
    if word_count < 6:
        print("--count must be >= 6 for this script's scenario", file=sys.stderr)
        return 1

    print(f"using scratch db: {_SCRATCH_DB}")
    print(f"seeding {word_count} test lexemes into one shared deck")
    init_db()

    try:
        publisher_id = create_user("policy-publisher@lexeme-status-policy-regression.test", "PolicyPublisher")
        importer_id = create_user("policy-importer@lexeme-status-policy-regression.test", "PolicyImporter")

        shared_deck_id = create_shared_deck(publisher_id, "SRS 상태 정책 회귀 테스트 덱")
        lexeme_ids = seed_lexeme_deck(shared_deck_id, word_count)

        # --- D1: import alone must not create progress/log/vocab_items rows -----
        before_import = snapshot(importer_id)
        imported = import_shared_deck(importer_id, shared_deck_id)
        if imported is None or imported.get("mode") != "subscribed":
            raise RegressionFailure("import_shared_deck did not report 'subscribed' mode")
        after_import = snapshot(importer_id)
        expect_delta("after import", before_import, after_import, "vocab_items", 0)
        expect_delta(
            "after import", before_import, after_import, "user_word_progress", 0
        )
        expect_delta(
            "after import", before_import, after_import, "lexeme_review_logs", 0
        )

        # --- D2: listing the study queue alone must not create rows either -------
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

        # --- A: first rating on a progress-less lexeme auto-corrects status ------
        again_id, hard_id, good_id, easy_id = lexeme_ids[0:4]
        rated_status_by_rating: dict[str, str] = {}
        for rating, lexeme_id in (
            ("again", again_id),
            ("hard", hard_id),
            ("good", good_id),
            ("easy", easy_id),
        ):
            progress = record_lexeme_review(
                importer_id, lexeme_id, rating, shared_deck_id=shared_deck_id
            )
            if progress is None:
                raise RegressionFailure(f"record_lexeme_review returned None for rating={rating}")
            expected_status = RATING_TO_EXPECTED_STATUS[rating]
            expect_equal(
                f"API response status after first '{rating}' rating",
                progress["status"],
                expected_status,
            )
            rated_status_by_rating[rating] = progress["status"]

            log_row = get_last_log_row(importer_id, lexeme_id)
            expect_equal(
                f"lexeme_review_logs.previous_status for first '{rating}' rating",
                log_row["previous_status"],
                "unclassified",
            )
            expect_equal(
                f"lexeme_review_logs.new_status for first '{rating}' rating",
                log_row["new_status"],
                expected_status,
            )

        after_first_ratings = snapshot(importer_id)
        expect_delta(
            "after 4 first-time ratings",
            after_listing,
            after_first_ratings,
            "user_word_progress",
            4,
        )
        expect_delta(
            "after 4 first-time ratings",
            after_listing,
            after_first_ratings,
            "lexeme_review_logs",
            4,
        )
        expect_delta(
            "after 4 first-time ratings", after_listing, after_first_ratings, "vocab_items", 0
        )

        # --- B: a manually-set status is never overwritten by a later rating -----
        manual_lexeme_id = lexeme_ids[4]
        manual_progress = update_word_status(importer_id, manual_lexeme_id, "known")
        if manual_progress is None or manual_progress.get("status") != "known":
            raise RegressionFailure("update_word_status did not set status to 'known'")
        reviewed_after_manual = record_lexeme_review(
            importer_id, manual_lexeme_id, "again", shared_deck_id=shared_deck_id
        )
        if reviewed_after_manual is None:
            raise RegressionFailure("record_lexeme_review returned None for manual_lexeme_id")
        expect_equal(
            "manually-set status survives an 'again' rating",
            reviewed_after_manual["status"],
            "known",
        )
        manual_log_row = get_last_log_row(importer_id, manual_lexeme_id)
        expect_equal(
            "lexeme_review_logs.previous_status for the manual-status word",
            manual_log_row["previous_status"],
            "known",
        )
        expect_equal(
            "lexeme_review_logs.new_status for the manual-status word (unchanged)",
            manual_log_row["new_status"],
            "known",
        )

        # --- C: the due/new blind spot is actually fixed --------------------------
        # The 'good'-rated word is now 'uncertain' -- push its next_review_at into
        # the past and confirm it now counts as due (it never would have before
        # this phase, since rating alone never moved it off 'unclassified').
        set_next_review_at_in_past(importer_id, good_id)
        stats_after_due_fixup = build_stats(importer_id)
        due_queue = list_subscribed_lexeme_study_items(importer_id, due_only=True)
        due_lexeme_ids = {item["lexeme_id"] for item in due_queue}
        if good_id not in due_lexeme_ids:
            raise RegressionFailure(
                "expected the 'good'-rated, now-uncertain, past-due lexeme to appear "
                "in the due-only study queue"
            )
        if easy_id in due_lexeme_ids:
            raise RegressionFailure(
                "the 'easy'-rated (now 'known') lexeme must never appear as due, "
                "regardless of next_review_at"
            )
        if stats_after_due_fixup["lexeme_due_count"] < 1:
            raise RegressionFailure(
                "expected /stats lexeme_due_count to include the now-due, "
                "auto-corrected 'uncertain' word"
            )

        new_queue_lexeme_ids = {
            item["lexeme_id"]
            for item in list_subscribed_lexeme_study_items(importer_id)
            if item["status"] == "unclassified"
        }
        for lexeme_id in (again_id, hard_id, good_id, easy_id, manual_lexeme_id):
            if lexeme_id in new_queue_lexeme_ids:
                raise RegressionFailure(
                    f"lexeme_id={lexeme_id} was rated/status-set but still shows as "
                    "'unclassified' (new) -- the auto-correction did not apply"
                )

    except RegressionFailure as failure:
        print()
        print("Lexeme SRS status policy regression FAILED.")
        print(f"  {failure}")
        return 1

    print()
    print("Lexeme SRS status policy regression passed.")
    print(f"again -> {rated_status_by_rating['again']}")
    print(f"hard -> {rated_status_by_rating['hard']}")
    print(f"good -> {rated_status_by_rating['good']}")
    print(f"easy -> {rated_status_by_rating['easy']}")
    print("manual status preserved: known -> again rating -> still known")
    print("due/new gap fixed: auto-corrected 'uncertain' word now counts as due")
    print("vocab_items delta: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
