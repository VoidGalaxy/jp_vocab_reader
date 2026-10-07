"""Storage regression check for Phase 3: subscribed shared-deck words in the
SRS study queue (see docs/architecture/shared-lexeme-progress-storage.md).

Guards that wiring subscribed lexeme words into the review/study flow did
NOT reintroduce the storage-growth problem the earlier phases fixed:

    1. Publishing + importing a shared deck still costs 0 vocab_items rows,
       exactly as check_shared_deck_publish_storage_regression.py already
       checks.
    2. Merely *listing* the study queue (list_subscribed_lexeme_study_items,
       GET /study-items/lexemes) never creates a user_word_progress row --
       progress creation only happens on an actual rating submission
       (POST /shared-decks/{id}/words/{lexeme_id}/review), exactly like the
       existing deck-detail view.
    3. Submitting one rating for one lexeme item lazily creates exactly one
       user_word_progress row and still leaves vocab_items untouched.
    4. Submitting a second rating for the *same* lexeme item updates that
       one row in place -- no duplicate user_word_progress rows.
    5. The study queue de-duplicates a lexeme that appears in more than one
       subscribed deck into a single card.
    6. A non-subscribed shared deck's words never leak into the study queue
       even if a caller passes its shared_deck_id explicitly.
    7. New vs due (current contract since 11c49f6, Phase 20 Round 1): a
       never-rated subscribed lexeme is a *new*/first-review target, not a
       due one. due_only must match /stats due_count at every step, a first
       "again" leaves the first-review queue and only becomes due once its
       scheduled next_review_at passes, and a status-only change (no rating)
       stays a first-review target.

The checks below only observe the existing SRS behavior; none of them change
the schedule, the rating meanings or the queue rules.

Runs entirely against a throwaway SQLite file (never backend/vocab.db, never
whatever DATABASE_URL is already set in the environment) so it's safe to run
anywhere, including CI, without ever touching a remote/Neon database.

Usage:
    cd backend
    .venv\\Scripts\\Activate.ps1   (or source .venv/bin/activate)
    python scripts/check_shared_deck_srs_regression.py
    python scripts/check_shared_deck_srs_regression.py --count 1000
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
_SCRATCH_DB = Path(tempfile.gettempdir()) / "jp_vocab_reader_srs_regression.db"
_SCRATCH_DB.unlink(missing_ok=True)
os.environ["DATABASE_URL"] = f"sqlite:///{_SCRATCH_DB.as_posix()}"

from datetime import datetime, timedelta, timezone  # noqa: E402

from app.database import get_connection, get_srs_interval, init_db, now_iso  # noqa: E402
from app.repositories.lexeme_repository import (  # noqa: E402
    add_word_to_shared_deck,
    get_subscribed_lexeme_stats_summary,
    is_lexeme_deck,
    list_subscribed_lexeme_study_items,
    record_lexeme_review,
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


def seed_lexeme_deck(shared_deck_id: int, word_count: int, prefix: str) -> list[int]:
    lexeme_ids: list[int] = []
    for i in range(word_count):
        base_form = f"{prefix}{i:04d}"
        lexeme_id = upsert_lexeme(
            surface=base_form,
            base_form=base_form,
            reading=f"よみ{prefix}{i:04d}",
            part_of_speech="명사",
            meaning_ko=f"뜻{prefix}{i:04d}",
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
        "user_deck_subscriptions": count_rows(
            "user_deck_subscriptions", "user_id = ?", (user_id,)
        ),
        "user_word_progress": count_rows(
            "user_word_progress", "user_id = ?", (user_id,)
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


def queue_ids(user_id: int, **kwargs) -> set[int]:
    return {
        item["lexeme_id"]
        for item in list_subscribed_lexeme_study_items(user_id, **kwargs)
    }


def expect_due_matches_stats(label: str, user_id: int) -> set[int]:
    due_ids = queue_ids(user_id, due_only=True)
    due_count = get_subscribed_lexeme_stats_summary(user_id)["due_count"]
    if len(due_ids) != due_count:
        raise RegressionFailure(
            f"{label}: due_only queue has {len(due_ids)} item(s) but /stats "
            f"due_count is {due_count}"
        )
    return due_ids


def progress_row(user_id: int, lexeme_id: int) -> dict:
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT status, review_level, next_review_at, last_reviewed_at
            FROM user_word_progress WHERE user_id = ? AND lexeme_id = ?
            """,
            (user_id, lexeme_id),
        ).fetchone()
    if row is None:
        raise RegressionFailure(f"expected a progress row for lexeme {lexeme_id}")
    return dict(row)


def expect_scheduled_gap(label: str, row: dict, level: int) -> None:
    reviewed = datetime.fromisoformat(row["last_reviewed_at"])
    scheduled = datetime.fromisoformat(row["next_review_at"])
    if scheduled - reviewed != get_srs_interval(level):
        raise RegressionFailure(
            f"{label}: expected next_review_at = last_reviewed_at + "
            f"{get_srs_interval(level)}, got {scheduled - reviewed}"
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

    print(f"using scratch db: {_SCRATCH_DB}")
    print(f"seeding {word_count} test lexemes into one shared deck")
    init_db()

    try:
        publisher_id = create_user("srs-publisher@srs-regression.test", "SrsPublisher")
        importer_id = create_user("srs-importer@srs-regression.test", "SrsImporter")

        shared_deck_id = create_shared_deck(publisher_id, "SRS 통합 회귀 테스트 덱")
        lexeme_ids = seed_lexeme_deck(shared_deck_id, word_count, prefix="語")
        if not is_lexeme_deck(shared_deck_id):
            raise RegressionFailure("seeded deck was not detected as lexeme-mode")

        # --- 1. import: 0 vocab_items, +1 subscription, 0 progress ------------
        before_import = snapshot(importer_id)
        imported = import_shared_deck(importer_id, shared_deck_id)
        if imported is None or imported.get("mode") != "subscribed":
            raise RegressionFailure("import_shared_deck did not report 'subscribed' mode")
        after_import = snapshot(importer_id)
        expect_delta("after import", before_import, after_import, "vocab_items", 0)
        expect_delta(
            "after import", before_import, after_import, "user_deck_subscriptions", 1
        )
        expect_delta("after import", before_import, after_import, "user_word_progress", 0)

        # --- 2. listing the study queue must not create progress rows ----------
        queue = list_subscribed_lexeme_study_items(importer_id)
        if len(queue) != word_count:
            raise RegressionFailure(
                f"expected {word_count} items in the study queue, got {len(queue)}"
            )
        if not all(item["status"] == "unclassified" for item in queue):
            raise RegressionFailure(
                "expected every never-touched lexeme to show status='unclassified' "
                "in the study queue"
            )
        after_listing = snapshot(importer_id)
        expect_delta(
            "after listing the study queue (no rating yet)",
            after_import,
            after_listing,
            "user_word_progress",
            0,
        )
        expect_delta(
            "after listing the study queue (no rating yet)",
            after_import,
            after_listing,
            "vocab_items",
            0,
        )

        # Never-touched lexemes are new, not due (contract since 11c49f6):
        # due_only returns none of them, matching /stats due_count = 0, and
        # the first-review queue returns all of them.
        due_ids = expect_due_matches_stats("before any rating", importer_id)
        if due_ids:
            raise RegressionFailure(
                "expected never-touched lexemes to be new, not due, got "
                f"{len(due_ids)} of {word_count} in the due_only queue"
            )
        if queue_ids(importer_id, first_review_only=True) != set(lexeme_ids):
            raise RegressionFailure(
                "expected every never-touched lexeme in the first_review_only queue"
            )
        if get_subscribed_lexeme_stats_summary(importer_id)["new_count"] != word_count:
            raise RegressionFailure("expected /stats new_count to equal the deck size")

        # --- 3. one rating -> exactly one lazily-created progress row -----------
        target_lexeme_id = lexeme_ids[0]
        reviewed = record_lexeme_review(importer_id, target_lexeme_id, "good")
        if reviewed is None or reviewed.get("review_level", 0) <= 0:
            raise RegressionFailure("record_lexeme_review did not advance review_level")
        after_first_rating = snapshot(importer_id)
        expect_delta(
            "after first rating",
            after_listing,
            after_first_rating,
            "user_word_progress",
            1,
        )
        expect_delta(
            "after first rating", after_listing, after_first_rating, "vocab_items", 0
        )

        # --- 4. rating the same item again updates in place, no duplicate ------
        reviewed_again = record_lexeme_review(importer_id, target_lexeme_id, "good")
        if reviewed_again is None:
            raise RegressionFailure("second record_lexeme_review call returned None")
        after_second_rating = snapshot(importer_id)
        expect_delta(
            "after second rating on the same item",
            after_first_rating,
            after_second_rating,
            "user_word_progress",
            0,
        )
        expect_delta(
            "after second rating on the same item",
            after_first_rating,
            after_second_rating,
            "vocab_items",
            0,
        )
        if reviewed_again["review_level"] <= reviewed["review_level"]:
            raise RegressionFailure(
                "expected review_level to keep advancing on repeated 'good' ratings, "
                f"got {reviewed['review_level']} -> {reviewed_again['review_level']}"
            )

        # --- 5. the rated item no longer shows as due-with-no-progress ----------
        queue_after_rating = list_subscribed_lexeme_study_items(importer_id)
        rated_item = next(
            item for item in queue_after_rating if item["lexeme_id"] == target_lexeme_id
        )
        if rated_item["status"] == "unclassified" and rated_item["review_level"] == 0:
            raise RegressionFailure(
                "expected the rated item's overlay to reflect its updated review_level"
            )

        # --- 5b. new vs due after a first rating or a status-only change -------
        if target_lexeme_id in queue_ids(importer_id, first_review_only=True):
            raise RegressionFailure("a rated word must leave the first_review_only queue")
        good_row = progress_row(importer_id, target_lexeme_id)
        expect_scheduled_gap("after two 'good' ratings", good_row, good_row["review_level"])
        if target_lexeme_id in expect_due_matches_stats("after 'good'", importer_id):
            raise RegressionFailure("a word just rated 'good' must not be due yet")

        # First rating 'again': unclassified -> unknown, level 0, scheduled
        # get_srs_interval(0) later; rated, so no longer a first-review target,
        # and not due until that time passes.
        again_lexeme_id = lexeme_ids[2]
        record_lexeme_review(importer_id, again_lexeme_id, "again")
        again_row = progress_row(importer_id, again_lexeme_id)
        if again_row["status"] != "unknown" or again_row["review_level"] != 0:
            raise RegressionFailure(
                "first 'again' should give status='unknown', review_level=0, got "
                f"{again_row['status']!r}/{again_row['review_level']}"
            )
        if again_row["last_reviewed_at"] is None:
            raise RegressionFailure("first 'again' must set last_reviewed_at")
        expect_scheduled_gap("after first 'again'", again_row, 0)
        if again_lexeme_id in queue_ids(importer_id, first_review_only=True):
            raise RegressionFailure(
                "a word whose first rating was 'again' must leave the first_review_only queue"
            )
        if again_lexeme_id in expect_due_matches_stats("right after 'again'", importer_id):
            raise RegressionFailure("a word just rated 'again' must not be due before its interval")

        # Simulate the scheduled time passing (scratch DB only): only then is
        # the word due, for both the queue and /stats.
        past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        with get_connection() as connection:
            connection.execute(
                "UPDATE user_word_progress SET next_review_at = ? WHERE user_id = ? AND lexeme_id = ?",
                (past, importer_id, again_lexeme_id),
            )
        if again_lexeme_id not in expect_due_matches_stats("after the 'again' interval", importer_id):
            raise RegressionFailure("an 'again' word must be due once next_review_at has passed")

        # Status-only change (classified in reading, never rated): creates a
        # progress row but no last_reviewed_at, so it stays a first-review
        # target, whichever status it was given.
        status_only = {"unknown": lexeme_ids[3], "known": lexeme_ids[4]}
        for status, lexeme_id in status_only.items():
            update_word_status(importer_id, lexeme_id, status)
            row = progress_row(importer_id, lexeme_id)
            if row["last_reviewed_at"] is not None or row["review_level"] != 0:
                raise RegressionFailure(f"status-only '{status}' must not look rated")
        first_review_ids = queue_ids(importer_id, first_review_only=True)
        for status, lexeme_id in status_only.items():
            if lexeme_id not in first_review_ids:
                raise RegressionFailure(
                    f"status-only '{status}' word must stay in the first_review_only queue"
                )
        if status_only["known"] in queue_ids(importer_id):
            raise RegressionFailure("the default study queue must keep excluding 'known' words")
        expect_due_matches_stats("after status-only changes", importer_id)

        # --- 6. de-duplication across two subscribed decks sharing a lexeme -----
        second_shared_deck_id = create_shared_deck(publisher_id, "SRS 중복 확인용 덱")
        shared_lexeme_id = lexeme_ids[1]
        add_word_to_shared_deck(second_shared_deck_id, shared_lexeme_id, 0)
        with get_connection() as connection:
            connection.execute(
                "UPDATE shared_decks SET vocab_count = 1 WHERE id = ?",
                (second_shared_deck_id,),
            )
        second_import = import_shared_deck(importer_id, second_shared_deck_id)
        if second_import is None or second_import.get("mode") != "subscribed":
            raise RegressionFailure("import of the second overlapping deck did not subscribe")

        merged_queue = list_subscribed_lexeme_study_items(importer_id)
        occurrences = sum(
            1 for item in merged_queue if item["lexeme_id"] == shared_lexeme_id
        )
        if occurrences != 1:
            raise RegressionFailure(
                "expected a lexeme shared by two subscribed decks to appear exactly "
                f"once in the merged study queue, appeared {occurrences} times"
            )

        # --- 7. a non-subscribed deck's words never leak in ---------------------
        stranger_id = create_user("srs-stranger@srs-regression.test", "SrsStranger")
        stranger_deck_id = create_shared_deck(stranger_id, "구독 안 한 덱")
        seed_lexeme_deck(stranger_deck_id, 5, prefix="非")
        leaked = list_subscribed_lexeme_study_items(
            importer_id, shared_deck_id=stranger_deck_id
        )
        if leaked:
            raise RegressionFailure(
                "a shared_deck_id the user never subscribed to must return an empty "
                f"study queue, got {len(leaked)} item(s)"
            )

    except RegressionFailure as failure:
        print()
        print("Shared deck SRS integration regression FAILED.")
        print(f"  {failure}")
        return 1

    print()
    print("Shared deck SRS integration regression passed.")
    print(f"vocab_items delta after import: 0")
    print(f"subscriptions delta after import: 1")
    print(f"progress delta after import: 0")
    print(f"progress delta after listing study queue: 0")
    print("never-touched lexemes: new (first-review queue), not due; due_only == /stats due_count")
    print("first 'again': leaves first-review queue, due only after its interval")
    print("status-only change: stays in first-review queue")
    print(f"progress delta after first rating: 1")
    print(f"progress delta after second rating on same item: 0 (updated in place)")
    print(f"vocab_items delta after rating: 0")
    print("de-duplicated lexeme shared by two subscribed decks: 1 study card")
    print("non-subscribed deck's words leaked into study queue: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
