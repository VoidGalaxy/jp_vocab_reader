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

from app.database import get_connection, init_db, now_iso  # noqa: E402
from app.repositories.lexeme_repository import (  # noqa: E402
    add_word_to_shared_deck,
    is_lexeme_deck,
    list_subscribed_lexeme_study_items,
    record_lexeme_review,
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

        due_queue = list_subscribed_lexeme_study_items(importer_id, due_only=True)
        if len(due_queue) != word_count:
            raise RegressionFailure(
                "expected every never-touched lexeme (next_review_at IS NULL) to count "
                f"as due, got {len(due_queue)} of {word_count}"
            )

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
    print(f"progress delta after first rating: 1")
    print(f"progress delta after second rating on same item: 0 (updated in place)")
    print(f"vocab_items delta after rating: 0")
    print("de-duplicated lexeme shared by two subscribed decks: 1 study card")
    print("non-subscribed deck's words leaked into study queue: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
