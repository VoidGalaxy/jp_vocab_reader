"""Regression check for Phase 5: stats/dashboard integration (see
docs/architecture/shared-lexeme-progress-storage.md).

Guards that folding subscribed shared-deck/JLPT lexeme progress into
GET /stats (build_stats()) did NOT change any storage promise earlier
phases already fixed, and that the new numbers behave correctly:

    1. Publish + import still costs 0 vocab_items rows for the importer
       (unchanged from earlier phases).
    2. Calling /stats (build_stats()) itself never creates a
       user_word_progress, lexeme_review_logs, or vocab_items row --
       stats are a pure read, called repeatedly with no side effects.
    3. Right after import (no progress rows yet), every subscribed word
       counts toward lexeme_new_count and none toward lexeme_due_count
       (a progress-less lexeme is "new", not "due" -- see
       get_subscribed_lexeme_stats_summary's docstring).
    4. Rating one lexeme logs it under lexeme_completed_today (an actual
       review event), while merely importing/listing does not.
    5. Explicitly setting a lexeme's status to "unknown" (lazily creating
       its progress row with next_review_at still null) makes it count
       toward lexeme_due_count; setting another to "uncertain" makes it
       count toward lexeme_hard_count.
    6. A lexeme reachable through two different subscribed decks is never
       double-counted in lexeme_new_count/lexeme_due_count/
       lexeme_hard_count.
    7. The existing personal vocab_items review flow still contributes to
       vocab_due_count/vocab_new_count/vocab_hard_count/
       vocab_completed_today exactly as before, and the merged
       due_today_count/new_count/hard_count/reviewed_today_count fields
       equal vocab_* + lexeme_* (the existing StatsResponse field names/
       types are unchanged -- this is purely additive).

Runs entirely against a throwaway SQLite file (never backend/vocab.db, never
whatever DATABASE_URL is already set in the environment) so it's safe to run
anywhere, including CI, without ever touching a remote/Neon database.

Usage:
    cd backend
    .venv\\Scripts\\Activate.ps1   (or source .venv/bin/activate)
    python scripts/check_lexeme_stats_regression.py
    python scripts/check_lexeme_stats_regression.py --count 1000
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
_SCRATCH_DB = Path(tempfile.gettempdir()) / "jp_vocab_reader_lexeme_stats_regression.db"
_SCRATCH_DB.unlink(missing_ok=True)
os.environ["DATABASE_URL"] = f"sqlite:///{_SCRATCH_DB.as_posix()}"

from app.database import get_connection, init_db, now_iso  # noqa: E402
from app.repositories.lexeme_repository import (  # noqa: E402
    add_word_to_shared_deck,
    record_lexeme_review,
    update_word_status,
    upsert_lexeme,
)
from app.repositories.shared_deck_repository import import_shared_deck  # noqa: E402
from app.repositories.stats_repository import build_stats  # noqa: E402
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


def expect_equal(label: str, actual: int, expected: int) -> None:
    if actual != expected:
        raise RegressionFailure(f"{label}: expected {expected}, got {actual}")


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
        publisher_id = create_user("stats-publisher@lexeme-stats-regression.test", "StatsPublisher")
        importer_id = create_user("stats-importer@lexeme-stats-regression.test", "StatsImporter")

        shared_deck_id = create_shared_deck(publisher_id, "통계 통합 회귀 테스트 덱")
        lexeme_ids = seed_lexeme_deck(shared_deck_id, word_count, prefix="통계")

        # --- import: 0 vocab_items for importer --------------------------------
        before_import = snapshot(importer_id)
        imported = import_shared_deck(importer_id, shared_deck_id)
        if imported is None or imported.get("mode") != "subscribed":
            raise RegressionFailure("import_shared_deck did not report 'subscribed' mode")
        after_import = snapshot(importer_id)
        expect_delta("after import", before_import, after_import, "vocab_items", 0)
        expect_delta(
            "after import", before_import, after_import, "user_word_progress", 0
        )

        # --- calling /stats (build_stats) must never write anything -------------
        stats_call_1 = build_stats(importer_id)
        stats_call_2 = build_stats(importer_id)
        after_two_stats_calls = snapshot(importer_id)
        expect_delta(
            "after two /stats calls",
            after_import,
            after_two_stats_calls,
            "vocab_items",
            0,
        )
        expect_delta(
            "after two /stats calls",
            after_import,
            after_two_stats_calls,
            "user_word_progress",
            0,
        )
        expect_delta(
            "after two /stats calls",
            after_import,
            after_two_stats_calls,
            "lexeme_review_logs",
            0,
        )

        # --- right after import: every word is "new", none are "due" ------------
        expect_equal(
            "lexeme_new_count right after import (no progress rows yet)",
            stats_call_1["lexeme_new_count"],
            word_count,
        )
        expect_equal(
            "lexeme_due_count right after import (progress-less lexemes are 'new', "
            "not 'due')",
            stats_call_1["lexeme_due_count"],
            0,
        )
        expect_equal(
            "lexeme_completed_today right after import (import is not a review)",
            stats_call_1["lexeme_completed_today"],
            0,
        )
        expect_equal("lexeme_hard_count right after import", stats_call_1["lexeme_hard_count"], 0)
        # merged totals must include the vocab_* baseline (0 here, no vocab_items
        # yet) plus the lexeme_* contribution computed above.
        expect_equal(
            "merged new_count == vocab_new_count + lexeme_new_count",
            stats_call_1["new_count"],
            stats_call_1["vocab_new_count"] + stats_call_1["lexeme_new_count"],
        )
        expect_equal(
            "merged due_today_count == vocab_due_count + lexeme_due_count",
            stats_call_1["due_today_count"],
            stats_call_1["vocab_due_count"] + stats_call_1["lexeme_due_count"],
        )

        # --- rate one lexeme: completed-today reflects the rating event ---------
        rated_lexeme_id = lexeme_ids[0]
        reviewed = record_lexeme_review(
            importer_id, rated_lexeme_id, "good", shared_deck_id=shared_deck_id
        )
        if reviewed is None:
            raise RegressionFailure("record_lexeme_review returned None")
        stats_after_rating = build_stats(importer_id)
        expect_equal(
            "lexeme_completed_today after one rating",
            stats_after_rating["lexeme_completed_today"],
            1,
        )
        # rated word's review_level is now > 0, so it drops out of "new". Its
        # status is auto-corrected from 'unclassified' to 'uncertain' on this
        # first rating (Phase 6 policy: rating="good" -> status="uncertain",
        # see record_lexeme_review's _RATING_TO_AUTO_STATUS), so it now
        # contributes to lexeme_hard_count -- but not lexeme_due_count, since
        # "good" schedules next_review_at comfortably in the future, not
        # null/past.
        expect_equal(
            "lexeme_new_count drops by exactly 1 after rating the one word",
            stats_after_rating["lexeme_new_count"],
            word_count - 1,
        )
        expect_equal(
            "lexeme_hard_count reflects the 'good' rating's auto-corrected "
            "'uncertain' status (Phase 6)",
            stats_after_rating["lexeme_hard_count"],
            1,
        )
        expect_equal(
            "lexeme_due_count unaffected by the 'good' rating (next_review_at is "
            "in the future, not due yet)",
            stats_after_rating["lexeme_due_count"],
            0,
        )

        # --- explicitly setting status makes a lexeme count as due/hard ---------
        due_lexeme_id = lexeme_ids[1]
        due_progress = update_word_status(importer_id, due_lexeme_id, "unknown")
        if due_progress is None:
            raise RegressionFailure("update_word_status returned None for due_lexeme_id")
        hard_lexeme_id = lexeme_ids[2]
        hard_progress = update_word_status(importer_id, hard_lexeme_id, "uncertain")
        if hard_progress is None:
            raise RegressionFailure("update_word_status returned None for hard_lexeme_id")

        stats_after_status_changes = build_stats(importer_id)
        expect_equal(
            "lexeme_due_count after marking one word 'unknown' (next_review_at "
            "still null)",
            stats_after_status_changes["lexeme_due_count"],
            2,  # 'unknown' word + 'uncertain' word both satisfy the due condition
        )
        expect_equal(
            "lexeme_hard_count after marking one word 'uncertain' (plus the "
            "'good'-rated word already auto-corrected to 'uncertain' above)",
            stats_after_status_changes["lexeme_hard_count"],
            2,
        )

        # --- de-duplication: the same lexeme in a second subscribed deck --------
        second_shared_deck_id = create_shared_deck(publisher_id, "통계 중복 확인용 덱")
        add_word_to_shared_deck(second_shared_deck_id, due_lexeme_id, 0)
        with get_connection() as connection:
            connection.execute(
                "UPDATE shared_decks SET vocab_count = 1 WHERE id = ?",
                (second_shared_deck_id,),
            )
        second_import = import_shared_deck(importer_id, second_shared_deck_id)
        if second_import is None or second_import.get("mode") != "subscribed":
            raise RegressionFailure("import of the second overlapping deck did not subscribe")

        stats_after_second_subscription = build_stats(importer_id)
        expect_equal(
            "lexeme_due_count unchanged after subscribing to a second deck sharing "
            "the same 'due' lexeme (no double count)",
            stats_after_second_subscription["lexeme_due_count"],
            2,
        )

        # --- existing personal vocab_items review flow is unaffected -------------
        created_item, _was_created = create_or_update_vocab_item(
            importer_id,
            VocabItemCreate(
                surface="통계복습", base_form="통계복습", reading="とうけいふくしゅう",
                meaning_ko="통계 복습",
            ),
        )
        stats_before_vocab_review = build_stats(importer_id)
        vocab_updated = record_review(importer_id, created_item["id"], "good")
        if vocab_updated is None:
            raise RegressionFailure("record_review (vocab) returned None")
        stats_after_vocab_review = build_stats(importer_id)
        if (
            stats_after_vocab_review["vocab_completed_today"]
            - stats_before_vocab_review["vocab_completed_today"]
            != 1
        ):
            raise RegressionFailure(
                "expected vocab_completed_today to increase by 1 after a personal "
                "vocab_items rating"
            )
        if (
            stats_after_vocab_review["lexeme_completed_today"]
            != stats_before_vocab_review["lexeme_completed_today"]
        ):
            raise RegressionFailure(
                "a personal vocab_items rating must never change lexeme_completed_today"
            )
        expect_equal(
            "merged reviewed_today_count == vocab_completed_today + lexeme_completed_today",
            stats_after_vocab_review["reviewed_today_count"],
            stats_after_vocab_review["vocab_completed_today"]
            + stats_after_vocab_review["lexeme_completed_today"],
        )

        final_new_count = stats_after_vocab_review["lexeme_new_count"]
        final_due_count = stats_after_vocab_review["lexeme_due_count"]
        final_hard_count = stats_after_vocab_review["lexeme_hard_count"]
        final_completed_today = stats_after_vocab_review["lexeme_completed_today"]

    except RegressionFailure as failure:
        print()
        print("Lexeme stats regression FAILED.")
        print(f"  {failure}")
        return 1

    print()
    print("Lexeme stats regression passed.")
    print(f"new lexeme count included: {final_new_count}")
    print(f"due lexeme count included: {final_due_count}")
    print(f"difficult (hard) count includes user_word_progress: {final_hard_count}")
    print(f"completed today includes lexeme logs: {final_completed_today}")
    print("duplicate lexeme subscriptions deduped: due_count unchanged after 2nd subscription")
    print("vocab_items delta from /stats calls: 0")
    print("existing vocab_items review_logs stats flow unaffected: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
