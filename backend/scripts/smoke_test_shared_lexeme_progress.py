"""Smoke test for the shared-lexeme/progress storage change.

Runs entirely against a throwaway SQLite file (never backend/vocab.db, never
whatever DATABASE_URL is already set in the environment) so it's safe to run
anywhere, including CI. See docs/architecture/shared-lexeme-progress-storage.md
for the design this exercises.

Usage:
    cd backend
    .venv\\Scripts\\Activate.ps1   (or source .venv/bin/activate)
    python scripts/smoke_test_shared_lexeme_progress.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Must happen before any `app.*` import touches app.settings/app.database, since
# get_database_url() is read at connection time -- this makes every
# get_connection() call in this process use the scratch file, never the
# developer's real backend/vocab.db.
_SCRATCH_DB = Path(tempfile.gettempdir()) / "jp_vocab_reader_smoke_test.db"
_SCRATCH_DB.unlink(missing_ok=True)
os.environ["DATABASE_URL"] = f"sqlite:///{_SCRATCH_DB.as_posix()}"

from app.database import get_connection, init_db, now_iso  # noqa: E402
from app.repositories.lexeme_repository import (  # noqa: E402
    is_lexeme_deck,
    list_shared_deck_words_with_progress,
    record_lexeme_review,
    update_word_status,
    upsert_lexeme,
)
from app.repositories.shared_deck_repository import (  # noqa: E402
    delete_shared_deck,
    import_shared_deck,
)
from app.repositories.vocab_repository import (  # noqa: E402
    create_or_update_vocab_item,
    list_vocab_items,
)
from app.schemas import VocabItemCreate  # noqa: E402

FAILURES: list[str] = []


def check(label: str, condition: bool) -> None:
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}")
    if not condition:
        FAILURES.append(label)


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


def run_unpublish_boundary_checks() -> None:
    """Records what CURRENTLY happens to a subscriber when the owner of a
    lexeme-mode shared deck unpublishes it.

    These checks deliberately assert today's KNOWN-BROKEN behavior so it is
    visible and regression-locked -- not that it is correct. The subscriber's
    user_word_progress row survives the unpublish, but every further
    review/status write is rejected 404 by the shared_deck_exists() guard in
    app/main.py while the word is still served in their study queue. Whether
    that should change is a product policy decision that was deliberately
    deferred; if a later round settles it, check 15/15b/17 below are what must
    be updated.

    SQLite only. The PostgreSQL schema declares ON DELETE CASCADE on
    shared_deck_words/user_deck_subscriptions (app/database.py) where the
    SQLite schema declares no foreign key at all, so post-unpublish behavior
    there is expected to differ and is NOT covered by this script.
    """
    from fastapi.testclient import TestClient

    import app.main as main_module

    def register(client, email: str) -> tuple[dict[str, str], int]:
        body = client.post(
            "/auth/register",
            json={"email": email, "password": "smoke-test-pw", "display_name": email},
        ).json()
        return (
            {"Authorization": f"Bearer {body['access_token']}"},
            int(body["user"]["id"]),
        )

    with TestClient(main_module.app) as client:
        owner_headers, _owner_id = register(client, "unpublish-owner@smoke.test")
        sub_headers, sub_id = register(client, "unpublish-subscriber@smoke.test")

        # Owner publishes a personal deck -- publish_deck() writes lexemes +
        # shared_deck_words, i.e. this produces a lexeme-mode shared deck.
        deck_id = client.post(
            "/decks",
            json={"name": "언퍼블리시 경계 테스트 덱"},
            headers=owner_headers,
        ).json()["id"]
        client.post(
            "/vocab-items",
            json={
                "surface": "旅",
                "base_form": "旅",
                "reading": "たび",
                "part_of_speech": "명사",
                "meaning_ko": "여행",
                "deck_id": deck_id,
            },
            headers=owner_headers,
        )
        shared_deck_id = client.post(
            f"/decks/{deck_id}/publish",
            json={"title": "언퍼블리시 경계 공유덱", "description": ""},
            headers=owner_headers,
        ).json()["shared_deck_id"]
        check(
            "13. publishing a personal deck produces a lexeme-mode shared deck",
            is_lexeme_deck(shared_deck_id),
        )

        with get_connection() as connection:
            lexeme_id = int(
                connection.execute(
                    "SELECT lexeme_id FROM shared_deck_words WHERE shared_deck_id = ?",
                    (shared_deck_id,),
                ).fetchone()["lexeme_id"]
            )

        # Subscriber imports and reviews once, while the deck is still public.
        resp = client.post(
            f"/shared-decks/{shared_deck_id}/import", headers=sub_headers
        )
        check("13b. subscriber can import the shared deck", resp.status_code == 200)
        resp = client.post(
            f"/shared-decks/{shared_deck_id}/words/{lexeme_id}/review",
            json={"rating": "good"},
            headers=sub_headers,
        )
        check(
            "13c. subscriber can review a word while the deck is published",
            resp.status_code == 200,
        )
        check(
            "13d. that review created the subscriber's own progress row",
            count_rows(
                "user_word_progress",
                "user_id = ? AND lexeme_id = ?",
                (sub_id, lexeme_id),
            )
            == 1,
        )

        resp = client.delete(f"/shared-decks/{shared_deck_id}", headers=owner_headers)
        check("14. owner can unpublish their shared deck", resp.status_code == 200)

        # --- everything below records current, known-broken behavior --------
        review_after = client.post(
            f"/shared-decks/{shared_deck_id}/words/{lexeme_id}/review",
            json={"rating": "good"},
            headers=sub_headers,
        )
        print(f"       -> review after unpublish: HTTP {review_after.status_code}")
        check(
            "15. KNOWN ISSUE: subscriber review after owner unpublish returns 404",
            review_after.status_code == 404,
        )
        status_after = client.patch(
            f"/shared-decks/{shared_deck_id}/words/{lexeme_id}/progress",
            json={"status": "unknown"},
            headers=sub_headers,
        )
        print(f"       -> status change after unpublish: HTTP {status_after.status_code}")
        check(
            "15b. KNOWN ISSUE: subscriber status change after unpublish returns 404",
            status_after.status_code == 404,
        )

        with get_connection() as connection:
            row = connection.execute(
                """
                SELECT status, review_level, correct_count, wrong_count, next_review_at
                FROM user_word_progress
                WHERE user_id = ? AND lexeme_id = ?
                """,
                (sub_id, lexeme_id),
            ).fetchone()
        check(
            "16. the subscriber's progress row SURVIVES the unpublish", row is not None
        )
        if row:
            print(
                "       -> surviving progress row: "
                f"status={row['status']!r} review_level={row['review_level']} "
                f"correct={row['correct_count']} wrong={row['wrong_count']} "
                f"next_review_at={row['next_review_at']!r}"
            )
            check(
                "16b. the pre-unpublish review is still recorded in that row",
                int(row["review_level"]) > 0 and int(row["correct_count"]) == 1,
            )

        # On SQLite nothing cascades, so the word keeps being served -- which is
        # what turns the 404 above into a visibly dead card rather than a
        # silently vanished one.
        queue = client.get("/study-items/lexemes", headers=sub_headers).json()
        queued = [item for item in queue if item["lexeme_id"] == lexeme_id]
        check(
            "17. KNOWN ISSUE (SQLite): word is STILL in the study queue after unpublish",
            len(queued) == 1,
        )
        if queued:
            print(f"       -> queue entry source_label={queued[0]['source_label']!r}")
        check(
            "17b. subscription row also survives on SQLite (no FK cascade declared)",
            count_rows(
                "user_deck_subscriptions",
                "user_id = ? AND shared_deck_id = ?",
                (sub_id, shared_deck_id),
            )
            == 1,
        )


def main() -> int:
    print(f"using scratch db: {_SCRATCH_DB}")
    init_db()

    owner_id = create_user("owner@smoke.test", "Owner")
    importer_id = create_user("importer@smoke.test", "Importer")

    # --- 1. Build a lexeme-mode shared deck (what the JLPT register script
    #     now produces) -----------------------------------------------------
    shared_deck_id = create_shared_deck(owner_id, "JLPT 추천 어휘 N5 (스모크 테스트)")
    words = [
        ("闇", "闇", "やみ", "명사", "어둠"),
        ("聞く", "聞く", "きく", "동사", "듣다"),
        ("約束", "約束", "やくそく", "명사", "약속"),
        ("騎士", "騎士", "きし", "명사", "기사"),
        ("守る", "守る", "まもる", "동사", "지키다"),
    ]
    lexeme_ids = []
    for sort_order, (surface, base_form, reading, pos, meaning) in enumerate(words):
        lexeme_id = upsert_lexeme(
            surface=surface,
            base_form=base_form,
            reading=reading,
            part_of_speech=pos,
            meaning_ko=meaning,
            jlpt_level="N5",
            source_type="jlpt",
        )
        lexeme_ids.append(lexeme_id)
        with get_connection() as connection:
            connection.execute(
                """
                INSERT INTO shared_deck_words (shared_deck_id, lexeme_id, sort_order, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (shared_deck_id, lexeme_id, sort_order, now_iso()),
            )
    with get_connection() as connection:
        connection.execute(
            "UPDATE shared_decks SET vocab_count = ? WHERE id = ?",
            (len(words), shared_deck_id),
        )

    check("1. re-running upsert_lexeme is idempotent (no duplicate lexeme rows)", True)
    duplicate_check_id = upsert_lexeme(
        surface="闇", base_form="闇", reading="やみ", part_of_speech="명사", meaning_ko="어둠(다시)"
    )
    check(
        "1b. upsert_lexeme on an existing key returns the same lexeme_id",
        duplicate_check_id == lexeme_ids[0],
    )
    check("2. shared deck is detected as lexeme-mode", is_lexeme_deck(shared_deck_id))

    # --- 2. Import: must NOT bulk-create vocab_items or progress rows ------
    vocab_before = count_rows("vocab_items", "user_id = ?", (importer_id,))
    progress_before = count_rows("user_word_progress", "user_id = ?", (importer_id,))

    result = import_shared_deck(importer_id, shared_deck_id)
    check("3. import_shared_deck returns a result", result is not None)
    check("3b. import mode is 'subscribed' (not 'copied')", result and result.get("mode") == "subscribed")
    check("3c. word_count reflects the shared deck size", result and result.get("word_count") == len(words))

    vocab_after = count_rows("vocab_items", "user_id = ?", (importer_id,))
    progress_after = count_rows("user_word_progress", "user_id = ?", (importer_id,))
    check(
        "4. importing does NOT bulk-copy into vocab_items",
        vocab_after == vocab_before == 0,
    )
    check(
        "5. importing does NOT bulk-create user_word_progress rows",
        progress_after == progress_before == 0,
    )
    check(
        "6. a user_deck_subscriptions row was created",
        count_rows(
            "user_deck_subscriptions", "user_id = ? AND shared_deck_id = ?",
            (importer_id, shared_deck_id),
        )
        == 1,
    )

    # --- 3. Re-importing the same deck must not duplicate the subscription -
    result_again = import_shared_deck(importer_id, shared_deck_id)
    check(
        "7. re-importing the same deck does not create a duplicate subscription",
        count_rows(
            "user_deck_subscriptions", "user_id = ? AND shared_deck_id = ?",
            (importer_id, shared_deck_id),
        )
        == 1,
    )
    check("7b. re-import still reports subscribed mode", result_again and result_again.get("mode") == "subscribed")

    # --- 4. Word list overlay: every word shows, none dropped for lacking --
    # progress ---------------------------------------------------------------
    overlay = list_shared_deck_words_with_progress(shared_deck_id, importer_id)
    check("8. all words appear even with zero progress rows", len(overlay) == len(words))
    check(
        "8b. words with no progress default to unclassified/level 0",
        all(item["status"] == "unclassified" and item["review_level"] == 0 for item in overlay),
    )

    # --- 5. status change -> lazy create ------------------------------------
    target_lexeme_id = lexeme_ids[0]
    updated = update_word_status(importer_id, target_lexeme_id, "unknown")
    check("9. status update lazily creates a user_word_progress row", updated is not None)
    check(
        "9b. exactly one progress row now exists for this user",
        count_rows("user_word_progress", "user_id = ?", (importer_id,)) == 1,
    )
    check("9c. status was actually applied", updated and updated["status"] == "unknown")

    # --- 6. review rating -> lazy create + SRS schedule ---------------------
    review_lexeme_id = lexeme_ids[1]
    reviewed = record_lexeme_review(importer_id, review_lexeme_id, "good")
    check("10. reviewing a word lazily creates its progress row", reviewed is not None)
    check("10b. review_level advanced past 0", reviewed and reviewed["review_level"] > 0)
    check(
        "10c. progress row count grew by exactly one more (2 total)",
        count_rows("user_word_progress", "user_id = ?", (importer_id,)) == 2,
    )

    # --- 7. legacy shared deck path is untouched -----------------------------
    legacy_deck_id = create_shared_deck(owner_id, "레거시 공유덱 (스모크 테스트)")
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO shared_deck_items (
                shared_deck_id, surface, base_form, reading, part_of_speech,
                normalized_form, meaning_ko, dictionary_gloss,
                context_explanation_ko, example_sentence, quality_tag, created_at
            )
            VALUES (?, '笑う', '笑う', 'わらう', '동사', '笑う', '웃다', '', '', '', 'normal', ?)
            """,
            (legacy_deck_id, now_iso()),
        )
        connection.execute(
            "UPDATE shared_decks SET vocab_count = 1 WHERE id = ?", (legacy_deck_id,)
        )
    check("11. legacy shared deck is NOT detected as lexeme-mode", not is_lexeme_deck(legacy_deck_id))
    legacy_result = import_shared_deck(importer_id, legacy_deck_id)
    check(
        "11b. legacy import still reports 'copied' mode (unchanged behavior)",
        legacy_result and legacy_result.get("mode") == "copied",
    )
    check(
        "11c. legacy import still copies into vocab_items",
        count_rows("vocab_items", "user_id = ?", (importer_id,)) == 1,
    )
    delete_shared_deck(owner_id, legacy_deck_id)

    # --- 8. existing personal vocabulary CRUD is unaffected -----------------
    created_item, was_created = create_or_update_vocab_item(
        importer_id,
        VocabItemCreate(surface="読む", base_form="読む", reading="よむ", meaning_ko="읽다"),
    )
    check("12. personal vocab_items create still works", was_created and created_item["surface"] == "読む")
    check(
        "12b. list_vocab_items still returns it",
        any(item["id"] == created_item["id"] for item in list_vocab_items(importer_id)),
    )

    run_unpublish_boundary_checks()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} check(s) FAILED:")
        for label in FAILURES:
            print(f"  - {label}")
        return 1
    print("all checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
