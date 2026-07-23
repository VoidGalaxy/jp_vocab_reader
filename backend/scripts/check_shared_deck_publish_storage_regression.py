"""Storage regression check for user-published shared decks.

Companion to check_shared_deck_storage_regression.py (JLPT-seeded decks).
Guards the same core promise for the OTHER way a shared deck gets created --
a real user publishing their own personal deck via
`POST /decks/{deck_id}/publish` (`publish_deck()` in
`app/repositories/shared_deck_repository.py`). See "User-published shared
decks are NOT yet lexeme-based" -> now fixed, in
docs/architecture/shared-lexeme-progress-storage.md.

Specifically checks:
    1. Publishing a deck of 100+ vocab_items (+ a handful of custom_terms)
       upserts everything into lexemes/shared_deck_words -- the publisher's
       own vocab_items/custom_terms rows are left completely untouched
       (still exist, unchanged count) and shared_deck_items/shared_deck_terms
       get zero new rows (no legacy copy for a brand new publish).
    2. The resulting shared deck is detected as lexeme-mode
       (is_lexeme_deck() -> True).
    3. A second user importing that deck only gets a user_deck_subscriptions
       row -- their vocab_items/custom_terms/user_word_progress counts do
       not move, regardless of deck size, and re-importing does not
       duplicate the subscription.
    4. A status change on one word lazily creates exactly one
       user_word_progress row and still does not touch vocab_items.
    5. custom_terms are not silently dropped: each one gets its own lexeme +
       shared_deck_words row and shows up in the deck's word list/overlay,
       with the term's own meaning intact.
    6. Two different publishers publishing decks that happen to share the
       same (base_form, reading, part_of_speech) word do NOT clobber each
       other's meaning: the shared lexemes.meaning_ko is set once (by
       whichever publish created it first) and never overwritten by a later
       publisher's personal wording, while each publisher's own deck still
       displays *their own* wording via the shared_deck_words
       display_meaning_ko snapshot (deck-specific override, checked with the
       overlay's display-priority resolution).

Runs entirely against a throwaway SQLite file (never backend/vocab.db, never
whatever DATABASE_URL is already set in the environment) so it's safe to run
anywhere, including CI, without ever touching a remote/Neon database.

Usage:
    cd backend
    .venv\\Scripts\\Activate.ps1   (or source .venv/bin/activate)
    python scripts/check_shared_deck_publish_storage_regression.py
    python scripts/check_shared_deck_publish_storage_regression.py --count 1000
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
_SCRATCH_DB = Path(tempfile.gettempdir()) / "jp_vocab_reader_publish_storage_regression.db"
_SCRATCH_DB.unlink(missing_ok=True)
os.environ["DATABASE_URL"] = f"sqlite:///{_SCRATCH_DB.as_posix()}"

from app.database import get_connection, init_db, now_iso  # noqa: E402
from app.repositories.lexeme_repository import (  # noqa: E402
    is_lexeme_deck,
    list_shared_deck_words_with_progress,
    update_word_status,
)
from app.repositories.shared_deck_repository import (  # noqa: E402
    get_shared_deck,
    import_shared_deck,
    publish_deck,
)

DEFAULT_WORD_COUNT = 200
CUSTOM_TERM_COUNT = 5


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


def create_personal_deck(user_id: int, name: str) -> int:
    timestamp = now_iso()
    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO decks (user_id, name, description, created_at, updated_at)
            VALUES (?, ?, '', ?, ?)
            """,
            (user_id, name, timestamp, timestamp),
        )
        return int(cursor.lastrowid)


def create_vocab_item(
    user_id: int,
    deck_id: int,
    surface: str,
    base_form: str,
    reading: str,
    part_of_speech: str,
    meaning_ko: str,
    example_sentence: str = "",
    context_explanation_ko: str = "",
) -> int:
    timestamp = now_iso()
    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO vocab_items (
                user_id, deck_id, surface, base_form, reading, part_of_speech,
                normalized_form, meaning_ko, dictionary_gloss, quality_tag,
                context_explanation_ko, example_sentence, status,
                correct_count, wrong_count, review_level, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, '', 'normal', ?, ?, 'unknown', 0, 0, 0, ?, ?)
            """,
            (
                user_id,
                deck_id,
                surface,
                base_form,
                reading,
                part_of_speech,
                base_form,
                meaning_ko,
                context_explanation_ko,
                example_sentence,
                timestamp,
                timestamp,
            ),
        )
        return int(cursor.lastrowid)


def create_custom_term(
    user_id: int,
    deck_id: int,
    term: str,
    reading: str,
    part_of_speech: str,
    meaning_ko: str,
    description: str = "",
) -> int:
    timestamp = now_iso()
    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO custom_terms (
                user_id, term, reading, part_of_speech, meaning_ko,
                description, deck_id, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, term, reading, part_of_speech, meaning_ko, description, deck_id, timestamp, timestamp),
        )
        return int(cursor.lastrowid)


def count_rows(table: str, where: str = "1=1", params: tuple = ()) -> int:
    with get_connection() as connection:
        row = connection.execute(
            f"SELECT COUNT(*) AS c FROM {table} WHERE {where}", params
        ).fetchone()
    return int(row["c"])


def snapshot(user_id: int) -> dict[str, int]:
    return {
        "vocab_items": count_rows("vocab_items", "user_id = ?", (user_id,)),
        "custom_terms": count_rows("custom_terms", "user_id = ?", (user_id,)),
        "lexemes": count_rows("lexemes"),
        "shared_deck_words": count_rows("shared_deck_words"),
        "shared_deck_items": count_rows("shared_deck_items"),
        "shared_deck_terms": count_rows("shared_deck_terms"),
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
        help=f"number of test vocab_items to seed into the publisher's deck "
        f"(default {DEFAULT_WORD_COUNT}, must be >= 100)",
    )
    args = parser.parse_args()
    word_count = args.count
    if word_count < 100:
        print(f"--count must be >= 100 (got {word_count})", file=sys.stderr)
        return 1

    print(f"using scratch db: {_SCRATCH_DB}")
    print(f"seeding {word_count} vocab_items + {CUSTOM_TERM_COUNT} custom_terms into publisher's deck")
    init_db()

    try:
        publisher_id = create_user("publisher@publish-storage-regression.test", "Publisher")
        importer_id = create_user("importer@publish-storage-regression.test", "Importer")
        publisher_deck_id = create_personal_deck(publisher_id, "공개용 개인 단어장")

        for i in range(word_count):
            create_vocab_item(
                publisher_id,
                publisher_deck_id,
                surface=f"公開語彙{i:04d}",
                base_form=f"公開語彙{i:04d}",
                reading=f"こうかいごい{i:04d}",
                part_of_speech="명사",
                meaning_ko=f"공개 단어 뜻{i:04d}",
                example_sentence=f"짧은 예문{i:04d}입니다.",
                context_explanation_ko=f"짧은 문맥 설명{i:04d}",
            )

        custom_term_ids = []
        for i in range(CUSTOM_TERM_COUNT):
            custom_term_ids.append(
                create_custom_term(
                    publisher_id,
                    publisher_deck_id,
                    term=f"커스텀용어{i}",
                    reading=f"かすたむ{i}",
                    part_of_speech="명사",
                    meaning_ko=f"커스텀 뜻{i}",
                    description=f"짧은 설명{i}",
                )
            )

        publisher_before = snapshot(publisher_id)

        # --- publish -----------------------------------------------------
        published = publish_deck(
            publisher_id, publisher_deck_id, title="공개 테스트 덱", description=""
        )
        if published is None:
            raise RegressionFailure("publish_deck returned None for a valid personal deck")
        shared_deck_id = published["shared_deck_id"]
        if published.get("vocab_count") != word_count:
            raise RegressionFailure(
                f"expected vocab_count={word_count} in publish response, got {published.get('vocab_count')}"
            )
        if published.get("custom_term_count") != CUSTOM_TERM_COUNT:
            raise RegressionFailure(
                f"expected custom_term_count={CUSTOM_TERM_COUNT} in publish response, "
                f"got {published.get('custom_term_count')}"
            )

        publisher_after_publish = snapshot(publisher_id)
        expect_delta(
            "after publish", publisher_before, publisher_after_publish, "vocab_items", 0
        )
        expect_delta(
            "after publish", publisher_before, publisher_after_publish, "custom_terms", 0
        )
        expect_delta(
            "after publish",
            publisher_before,
            publisher_after_publish,
            "shared_deck_items",
            0,
        )
        expect_delta(
            "after publish",
            publisher_before,
            publisher_after_publish,
            "shared_deck_terms",
            0,
        )
        expected_word_rows = word_count + CUSTOM_TERM_COUNT
        actual_word_rows = expect_delta(
            "after publish",
            publisher_before,
            publisher_after_publish,
            "shared_deck_words",
            expected_word_rows,
        )

        if not is_lexeme_deck(shared_deck_id):
            raise RegressionFailure(
                "publish_deck's shared deck was not detected as lexeme-mode "
                "(is_lexeme_deck returned False) -- shared_deck_words rows may not "
                "have been created correctly"
            )

        # --- custom_terms were not silently dropped -----------------------
        overlay = list_shared_deck_words_with_progress(shared_deck_id, importer_id)
        if len(overlay) != expected_word_rows:
            raise RegressionFailure(
                f"expected {expected_word_rows} words in the deck overlay "
                f"(vocab_items + custom_terms), got {len(overlay)}"
            )
        custom_term_surfaces = {f"커스텀용어{i}" for i in range(CUSTOM_TERM_COUNT)}
        found_custom_meanings = {
            item["surface"]: item["meaning_ko"]
            for item in overlay
            if item["surface"] in custom_term_surfaces
        }
        if len(found_custom_meanings) != CUSTOM_TERM_COUNT:
            raise RegressionFailure(
                f"expected all {CUSTOM_TERM_COUNT} custom_terms to appear in the deck "
                f"word list, found {len(found_custom_meanings)}"
            )
        for i in range(CUSTOM_TERM_COUNT):
            expected_meaning = f"커스텀 뜻{i}"
            actual_meaning = found_custom_meanings.get(f"커스텀용어{i}")
            if actual_meaning != expected_meaning:
                raise RegressionFailure(
                    f"custom term {i}: expected meaning_ko={expected_meaning!r}, "
                    f"got {actual_meaning!r}"
                )

        detail = get_shared_deck(shared_deck_id, importer_id)
        if detail is None:
            raise RegressionFailure("get_shared_deck returned None right after publish")
        if detail.get("custom_terms") != []:
            raise RegressionFailure(
                "expected custom_terms list to be empty for a lexeme-mode deck "
                "(merged into items instead), got "
                f"{detail.get('custom_terms')!r}"
            )
        if len(detail.get("items", [])) != expected_word_rows:
            raise RegressionFailure(
                f"expected {expected_word_rows} items in shared deck detail, "
                f"got {len(detail.get('items', []))}"
            )

        # --- meaning-overwrite protection ---------------------------------
        # A second publisher republishes a *different* personal deck that
        # happens to contain the exact same (base_form, reading,
        # part_of_speech) as the very first seeded vocab item, but with
        # their own different wording. The shared lexeme must keep its
        # original meaning; the second publisher's own deck must still show
        # their own wording via the deck-specific snapshot.
        second_publisher_id = create_user(
            "second_publisher@publish-storage-regression.test", "SecondPublisher"
        )
        second_deck_id = create_personal_deck(second_publisher_id, "두번째 공개용 단어장")
        create_vocab_item(
            second_publisher_id,
            second_deck_id,
            surface="公開語彙0000",
            base_form="公開語彙0000",
            reading="こうかいごい0000",
            part_of_speech="명사",
            meaning_ko="다른 사람이 붙인 다른 뜻",
        )
        second_published = publish_deck(
            second_publisher_id, second_deck_id, title="두번째 공개 테스트 덱", description=""
        )
        if second_published is None:
            raise RegressionFailure("second publish_deck call returned None")
        second_shared_deck_id = second_published["shared_deck_id"]

        lexeme_count_after_second_publish = count_rows(
            "lexemes",
            "base_form = ? AND reading = ? AND part_of_speech = ?",
            ("公開語彙0000", "こうかいごい0000", "명사"),
        )
        if lexeme_count_after_second_publish != 1:
            raise RegressionFailure(
                "expected exactly one shared lexeme row for the colliding word "
                f"(no duplicate created by the second publisher), found "
                f"{lexeme_count_after_second_publish}"
            )

        with get_connection() as connection:
            shared_meaning_row = connection.execute(
                """
                SELECT meaning_ko FROM lexemes
                WHERE base_form = ? AND reading = ? AND part_of_speech = ?
                """,
                ("公開語彙0000", "こうかいごい0000", "명사"),
            ).fetchone()
        if shared_meaning_row["meaning_ko"] != "공개 단어 뜻0000":
            raise RegressionFailure(
                "the shared lexemes.meaning_ko was overwritten by the second "
                "publisher's personal wording -- expected it to stay as the first "
                f"publisher's original meaning, got {shared_meaning_row['meaning_ko']!r}"
            )

        first_deck_overlay = {
            item["surface"]: item["meaning_ko"]
            for item in list_shared_deck_words_with_progress(shared_deck_id, importer_id)
        }
        second_deck_overlay = {
            item["surface"]: item["meaning_ko"]
            for item in list_shared_deck_words_with_progress(second_shared_deck_id, importer_id)
        }
        if first_deck_overlay.get("公開語彙0000") != "공개 단어 뜻0000":
            raise RegressionFailure(
                "first publisher's own deck should still display their own wording, got "
                f"{first_deck_overlay.get('公開語彙0000')!r}"
            )
        if second_deck_overlay.get("公開語彙0000") != "다른 사람이 붙인 다른 뜻":
            raise RegressionFailure(
                "second publisher's own deck should display their own wording via the "
                "deck-specific snapshot, not the shared lexeme's meaning, got "
                f"{second_deck_overlay.get('公開語彙0000')!r}"
            )

        # --- importer: import must not bulk-copy anything -----------------
        importer_before_import = snapshot(importer_id)
        import_result = import_shared_deck(importer_id, shared_deck_id)
        if import_result is None:
            raise RegressionFailure("import_shared_deck returned None for a valid deck id")
        if import_result.get("mode") != "subscribed":
            raise RegressionFailure(
                "expected import mode 'subscribed' for a user-published lexeme-mode deck, "
                f"got {import_result.get('mode')!r}"
            )
        importer_after_import = snapshot(importer_id)

        vocab_delta_import = expect_delta(
            "importer after import",
            importer_before_import,
            importer_after_import,
            "vocab_items",
            0,
        )
        custom_terms_delta_import = expect_delta(
            "importer after import",
            importer_before_import,
            importer_after_import,
            "custom_terms",
            0,
        )
        subscriptions_delta_import = expect_delta(
            "importer after import",
            importer_before_import,
            importer_after_import,
            "user_deck_subscriptions",
            1,
        )
        progress_delta_import = expect_delta(
            "importer after import",
            importer_before_import,
            importer_after_import,
            "user_word_progress",
            0,
        )

        # --- re-import must not duplicate the subscription ----------------
        reimport_result = import_shared_deck(importer_id, shared_deck_id)
        if reimport_result is None or reimport_result.get("mode") != "subscribed":
            raise RegressionFailure("re-importing the same deck did not report 'subscribed' mode")
        importer_after_reimport = snapshot(importer_id)
        expect_delta(
            "importer after re-import",
            importer_after_import,
            importer_after_reimport,
            "user_deck_subscriptions",
            0,
        )

        # --- status change on exactly one word -----------------------------
        target_word = overlay[0]
        updated = update_word_status(importer_id, target_word["lexeme_id"], "known")
        if updated is None or updated.get("status") != "known":
            raise RegressionFailure("update_word_status did not apply the new status")
        importer_after_status_update = snapshot(importer_id)

        progress_delta_status = expect_delta(
            "importer after status update",
            importer_after_reimport,
            importer_after_status_update,
            "user_word_progress",
            1,
        )
        vocab_delta_status = expect_delta(
            "importer after status update",
            importer_after_reimport,
            importer_after_status_update,
            "vocab_items",
            0,
        )

    except RegressionFailure as failure:
        print()
        print("User-published shared deck storage regression FAILED.")
        print(f"  {failure}")
        return 1

    print()
    print("User-published shared deck storage regression passed.")
    print(f"publisher vocab_items retained: {publisher_after_publish['vocab_items']} (unchanged)")
    print(f"publisher custom_terms retained: {publisher_after_publish['custom_terms']} (unchanged)")
    print(f"shared_deck_words created for publish: {actual_word_rows}")
    print("legacy shared_deck_items/shared_deck_terms rows created: 0")
    print(f"importer vocab_items delta after import: {vocab_delta_import}")
    print(f"importer custom_terms delta after import: {custom_terms_delta_import}")
    print(f"importer subscriptions delta after import: {subscriptions_delta_import}")
    print(f"importer progress delta after import: {progress_delta_import}")
    print(f"importer progress delta after status update: {progress_delta_status}")
    print(f"importer vocab_items delta after status update: {vocab_delta_status}")
    print("re-import duplicate subscriptions: 0 (idempotent)")
    print("colliding-word shared lexeme meaning: unchanged by second publisher (protected)")
    print("each publisher's own deck still shows their own wording (display_meaning_ko override)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
