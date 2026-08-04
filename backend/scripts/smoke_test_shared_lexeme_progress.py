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
    get_subscribed_lexeme_stats_summary,
    is_lexeme_deck,
    list_shared_deck_words_with_progress,
    list_subscribed_lexeme_study_items,
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
    """Verifies the owner-unpublish policy (see
    docs/architecture/shared-lexeme-progress-storage.md -- "owner unpublish
    policy", decided Phase 6 Round 0): unpublish means "closed to new
    users", not "existing subscribers lose their progress".

    delete_shared_deck() now soft-unpublishes -- it only flips
    shared_decks.visibility away from 'public', never deletes the row (or
    shared_deck_words/user_deck_subscriptions/user_word_progress). That is
    what lets an already-subscribed user keep reviewing the deck's words
    through their own subscription afterwards, with zero bulk-copy into
    personal vocab_items -- shared_deck_word_access_allowed() in
    shared_deck_repository.py allows review/status writes for a still-active
    subscriber even once the deck is unpublished. A brand new user is still
    fully blocked: list/detail/import all keep requiring
    visibility='public'.

    SQLite only (no PostgreSQL-only behavior left to special-case here --
    unpublish never hard-deletes shared_decks, so the ON DELETE CASCADE on
    shared_deck_words/user_deck_subscriptions in the PostgreSQL schema
    (app/database.py) is simply never triggered by this path on either
    database).
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
        other_deck_id = client.post(
            "/decks",
            json={"name": "언퍼블리시 교차 접근 테스트 덱"},
            headers=owner_headers,
        ).json()["id"]
        client.post(
            "/vocab-items",
            json={
                "surface": "森",
                "base_form": "森",
                "reading": "もり",
                "part_of_speech": "명사",
                "meaning_ko": "숲",
                "deck_id": other_deck_id,
            },
            headers=owner_headers,
        )
        other_shared_deck_id = client.post(
            f"/decks/{other_deck_id}/publish",
            json={"title": "언퍼블리시 교차 접근 공유덱", "description": ""},
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
            other_lexeme_id = int(
                connection.execute(
                    "SELECT lexeme_id FROM shared_deck_words WHERE shared_deck_id = ?",
                    (other_shared_deck_id,),
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
        cross_deck_review = client.post(
            f"/shared-decks/{shared_deck_id}/words/{other_lexeme_id}/review",
            json={"rating": "good"},
            headers=sub_headers,
        )
        check(
            "13e. public deck review is rejected when the lexeme is not in that deck",
            cross_deck_review.status_code == 404,
        )

        # Public (still-published) responses report is_published=True before
        # we flip visibility below -- confirms the field isn't just hardcoded.
        public_listing = client.get("/shared-decks", headers=sub_headers).json()
        public_listing_entry = next(
            item for item in public_listing if item["id"] == shared_deck_id
        )
        check(
            "13f. public deck list entry reports is_published=True",
            public_listing_entry["is_published"] is True,
        )
        public_detail = client.get(
            f"/shared-decks/{shared_deck_id}", headers=sub_headers
        ).json()
        check(
            "13g. public deck detail reports is_published=True",
            public_detail["is_published"] is True,
        )

        resp = client.delete(f"/shared-decks/{shared_deck_id}", headers=owner_headers)
        check("14. owner can unpublish their shared deck", resp.status_code == 200)

        # --- everything below verifies the decided owner-unpublish policy ----
        review_after = client.post(
            f"/shared-decks/{shared_deck_id}/words/{lexeme_id}/review",
            json={"rating": "good"},
            headers=sub_headers,
        )
        print(f"       -> review after unpublish: HTTP {review_after.status_code}")
        check(
            "15. existing subscriber can still review after owner unpublish (200)",
            review_after.status_code == 200,
        )
        status_after = client.patch(
            f"/shared-decks/{shared_deck_id}/words/{lexeme_id}/progress",
            json={"status": "unknown"},
            headers=sub_headers,
        )
        print(f"       -> status change after unpublish: HTTP {status_after.status_code}")
        check(
            "15b. existing subscriber can still change status after unpublish (200)",
            status_after.status_code == 200,
        )
        cross_deck_review_after = client.post(
            f"/shared-decks/{shared_deck_id}/words/{other_lexeme_id}/review",
            json={"rating": "good"},
            headers=sub_headers,
        )
        check(
            "15c. subscribed access still rejects a lexeme from another deck",
            cross_deck_review_after.status_code == 404,
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
                "16b. both the pre- and post-unpublish reviews landed on that row",
                int(row["review_level"]) > 0 and int(row["correct_count"]) == 2,
            )
            check(
                "16c. the post-unpublish status write actually landed",
                row["status"] == "unknown",
            )

        # No FK cascade is ever triggered by unpublish (it's a soft
        # visibility flip, never a shared_decks DELETE), so the word keeps
        # being served in the queue on both SQLite and PostgreSQL -- and,
        # unlike before this policy, that is now correct: the subscriber can
        # actually act on it (see 15/15b above), so it's a live card, not a
        # dead one.
        queue = client.get("/study-items/lexemes", headers=sub_headers).json()
        queued = [item for item in queue if item["lexeme_id"] == lexeme_id]
        check(
            "17. word stays in the study queue after unpublish (still reviewable)",
            len(queued) == 1,
        )
        if queued:
            print(f"       -> queue entry source_label={queued[0]['source_label']!r}")
        check(
            "17b. subscription row survives the unpublish",
            count_rows(
                "user_deck_subscriptions",
                "user_id = ? AND shared_deck_id = ?",
                (sub_id, shared_deck_id),
            )
            == 1,
        )
        check(
            "17c. shared_decks row itself survives (soft-unpublish, not hard delete)",
            count_rows("shared_decks", "id = ?", (shared_deck_id,)) == 1,
        )
        check(
            "17d. shared_decks.visibility flipped away from 'public'",
            count_rows(
                "shared_decks", "id = ? AND visibility = 'public'", (shared_deck_id,)
            )
            == 0,
        )

        # --- Phase 7 Round 1: owner/subscriber list+detail access reopens ----
        # (see docs/architecture/shared-lexeme-progress-storage.md -- "Owner
        # unpublish policy" Round 1 update). Unpublish no longer hides the
        # deck from the owner's own bookshelf or an existing subscriber's
        # SharedDeckSection list/detail -- only a brand new user stays
        # locked out (checked further below).
        owner_listing_after = client.get("/shared-decks", headers=owner_headers).json()
        owner_listing_entry = next(
            (item for item in owner_listing_after if item["id"] == shared_deck_id),
            None,
        )
        check(
            "19. owner's own list shows the deck again after unpublish",
            owner_listing_entry is not None,
        )
        check(
            "19b. that list entry reports is_published=False",
            owner_listing_entry is not None
            and owner_listing_entry["is_published"] is False,
        )
        owner_detail_after = client.get(
            f"/shared-decks/{shared_deck_id}", headers=owner_headers
        )
        check(
            "20. owner's own detail is 200 again after unpublish",
            owner_detail_after.status_code == 200,
        )
        check(
            "20b. that detail reports is_published=False",
            owner_detail_after.status_code == 200
            and owner_detail_after.json()["is_published"] is False,
        )

        sub_listing_after = client.get("/shared-decks", headers=sub_headers).json()
        sub_listing_entry = next(
            (item for item in sub_listing_after if item["id"] == shared_deck_id),
            None,
        )
        check(
            "21. existing subscriber's list shows the deck again after unpublish",
            sub_listing_entry is not None,
        )
        check(
            "21b. that list entry reports is_published=False",
            sub_listing_entry is not None and sub_listing_entry["is_published"] is False,
        )
        sub_detail_after = client.get(
            f"/shared-decks/{shared_deck_id}", headers=sub_headers
        )
        check(
            "22. existing subscriber's detail is 200 again after unpublish",
            sub_detail_after.status_code == 200,
        )
        check(
            "22b. that detail reports is_published=False",
            sub_detail_after.status_code == 200
            and sub_detail_after.json()["is_published"] is False,
        )

        # --- a brand new user must still be fully locked out -----------------
        new_headers, _new_user_id = register(client, "unpublish-newcomer@smoke.test")
        listing = client.get("/shared-decks", headers=new_headers).json()
        check(
            "18. unpublished deck no longer appears in the public list",
            all(item["id"] != shared_deck_id for item in listing),
        )
        detail_resp = client.get(
            f"/shared-decks/{shared_deck_id}", headers=new_headers
        )
        check(
            "18b. a new user gets 404 on the unpublished deck's detail",
            detail_resp.status_code == 404,
        )
        import_resp = client.post(
            f"/shared-decks/{shared_deck_id}/import", headers=new_headers
        )
        check(
            "18c. a new user cannot import the unpublished deck (404)",
            import_resp.status_code == 404,
        )

        # --- Phase 7 Round 5: owner republish (see
        # docs/architecture/shared-lexeme-progress-storage.md -- "Owner
        # unpublish policy" republish decision). republish_shared_deck() is a
        # pure visibility flip back to 'public', the mirror image of
        # delete_shared_deck() -- nothing else (subscriptions, progress,
        # shared_deck_words) should move.
        non_owner_republish = client.post(
            f"/shared-decks/{shared_deck_id}/republish", headers=sub_headers
        )
        check(
            "23. a non-owner cannot republish someone else's deck (403)",
            non_owner_republish.status_code == 403,
        )
        missing_republish = client.post(
            "/shared-decks/999999999/republish", headers=owner_headers
        )
        check(
            "23b. republishing a nonexistent shared deck is 404",
            missing_republish.status_code == 404,
        )

        with get_connection() as connection:
            progress_before_republish = connection.execute(
                """
                SELECT status, review_level, correct_count, wrong_count
                FROM user_word_progress
                WHERE user_id = ? AND lexeme_id = ?
                """,
                (sub_id, lexeme_id),
            ).fetchone()

        republish_resp = client.post(
            f"/shared-decks/{shared_deck_id}/republish", headers=owner_headers
        )
        check(
            "24. owner can republish their own unpublished deck (200)",
            republish_resp.status_code == 200,
        )
        check(
            "24b. shared_decks.visibility is back to 'public'",
            count_rows(
                "shared_decks", "id = ? AND visibility = 'public'", (shared_deck_id,)
            )
            == 1,
        )

        owner_listing_republished = client.get(
            "/shared-decks", headers=owner_headers
        ).json()
        owner_entry_republished = next(
            (item for item in owner_listing_republished if item["id"] == shared_deck_id),
            None,
        )
        check(
            "25. republished deck reappears in owner's list with is_published=True",
            owner_entry_republished is not None
            and owner_entry_republished["is_published"] is True,
        )

        sub_listing_republished = client.get("/shared-decks", headers=sub_headers).json()
        sub_entry_republished = next(
            (item for item in sub_listing_republished if item["id"] == shared_deck_id),
            None,
        )
        check(
            "26. republished deck reappears in subscriber's list with is_published=True",
            sub_entry_republished is not None
            and sub_entry_republished["is_published"] is True,
        )

        new_listing_republished = client.get("/shared-decks", headers=new_headers).json()
        new_entry_republished = next(
            (item for item in new_listing_republished if item["id"] == shared_deck_id),
            None,
        )
        check(
            "27. republished deck now appears in a brand new user's public list too",
            new_entry_republished is not None
            and new_entry_republished["is_published"] is True,
        )
        new_detail_republished = client.get(
            f"/shared-decks/{shared_deck_id}", headers=new_headers
        )
        check(
            "27b. a brand new user's detail is 200 again after republish",
            new_detail_republished.status_code == 200,
        )

        new_import_republished = client.post(
            f"/shared-decks/{shared_deck_id}/import", headers=new_headers
        )
        check(
            "28. a brand new user can import the deck again after republish (200)",
            new_import_republished.status_code == 200,
        )
        check(
            "28b. that import created a subscription (no vocab_items copy)",
            count_rows(
                "user_deck_subscriptions",
                "user_id = ? AND shared_deck_id = ?",
                (_new_user_id, shared_deck_id),
            )
            == 1,
        )

        with get_connection() as connection:
            progress_after_republish = connection.execute(
                """
                SELECT status, review_level, correct_count, wrong_count
                FROM user_word_progress
                WHERE user_id = ? AND lexeme_id = ?
                """,
                (sub_id, lexeme_id),
            ).fetchone()
        check(
            "29. the existing subscriber's progress row is untouched by republish",
            progress_before_republish is not None
            and progress_after_republish is not None
            and dict(progress_before_republish) == dict(progress_after_republish),
        )
        check(
            "29b. shared_deck_words row for this deck still exists",
            count_rows(
                "shared_deck_words",
                "shared_deck_id = ? AND lexeme_id = ?",
                (shared_deck_id, lexeme_id),
            )
            == 1,
        )
        check(
            "29c. the original subscriber's subscription row still exists",
            count_rows(
                "user_deck_subscriptions",
                "user_id = ? AND shared_deck_id = ?",
                (sub_id, shared_deck_id),
            )
            == 1,
        )

        review_after_republish = client.post(
            f"/shared-decks/{shared_deck_id}/words/{lexeme_id}/review",
            json={"rating": "good"},
            headers=sub_headers,
        )
        check(
            "30. existing subscriber can still review after republish (200)",
            review_after_republish.status_code == 200,
        )


def run_new_lexeme_limit_checks() -> None:
    """Phase 20 Round 2: the "new word" session's limit param, exercised
    against a deck big enough (50 words) to actually distinguish a real cap
    from a coincidentally-small fixture. Mirrors the JLPT N1 flooding
    scenario (Round 0/1) at a smaller, fast-to-run scale.

    Uses a dedicated user/deck so it doesn't interact with the shared 5-word
    fixture and its progress-row assertions used earlier in main().
    """
    from fastapi.testclient import TestClient

    import app.main as main_module

    owner_id = create_user("limit-owner@smoke.test", "Limit Owner")
    limit_user_id = create_user("limit-subscriber@smoke.test", "Limit Subscriber")
    shared_deck_id = create_shared_deck(owner_id, "대형 lexeme 상한 테스트 덱")

    word_count = 50
    lexeme_ids: list[int] = []
    for sort_order in range(word_count):
        lexeme_id = upsert_lexeme(
            surface=f"단어{sort_order}",
            base_form=f"단어{sort_order}",
            reading=f"たんご{sort_order}",
            part_of_speech="명사",
            meaning_ko=f"단어뜻{sort_order}",
            jlpt_level="N1",
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
            (word_count, shared_deck_id),
        )

    import_result = import_shared_deck(limit_user_id, shared_deck_id)
    check(
        "31. limit-check fixture: import subscribes without bulk-copy",
        import_result and import_result.get("mode") == "subscribed",
    )
    check(
        "31b. limit-check fixture: importing did not pre-create progress rows",
        count_rows("user_word_progress", "user_id = ?", (limit_user_id,)) == 0,
    )

    # --- repository layer: limit applied, limit omitted, limit + due_only --
    limited_items = list_subscribed_lexeme_study_items(
        limit_user_id, shared_deck_id=shared_deck_id, limit=30
    )
    check(
        "32. list_subscribed_lexeme_study_items(limit=30) returns exactly 30 of 50 new words",
        len(limited_items) == 30,
    )
    check(
        "32b. the 30 returned are the first 30 by sort_order (stable ordering)",
        [item["lexeme_id"] for item in limited_items] == lexeme_ids[:30],
    )

    unlimited_items = list_subscribed_lexeme_study_items(
        limit_user_id, shared_deck_id=shared_deck_id
    )
    check(
        "33. list_subscribed_lexeme_study_items(limit=None) still returns all 50 (unchanged default)",
        len(unlimited_items) == word_count,
    )

    due_only_with_limit = list_subscribed_lexeme_study_items(
        limit_user_id, shared_deck_id=shared_deck_id, due_only=True, limit=30
    )
    check(
        "34. due_only=true + limit=30 still returns 0 (Round 1 due definition preserved, "
        "not just masked by the limit)",
        len(due_only_with_limit) == 0,
    )

    # --- HTTP layer: GET /study-items/lexemes -------------------------------
    with TestClient(main_module.app) as client:
        register_resp = client.post(
            "/auth/register",
            json={
                "email": "limit-http-subscriber@smoke.test",
                "password": "smoke-test-pw",
                "display_name": "Limit HTTP Subscriber",
            },
        ).json()
        http_headers = {"Authorization": f"Bearer {register_resp['access_token']}"}

        import_resp = client.post(
            f"/shared-decks/{shared_deck_id}/import", headers=http_headers
        )
        check("35. HTTP import succeeds for the limit-check deck", import_resp.status_code == 200)

        limited_resp = client.get(
            "/study-items/lexemes",
            params={"shared_deck_id": shared_deck_id, "limit": 30},
            headers=http_headers,
        )
        check("36. GET /study-items/lexemes?limit=30 succeeds", limited_resp.status_code == 200)
        check(
            "36b. GET /study-items/lexemes?limit=30 returns exactly 30 items",
            len(limited_resp.json()) == 30,
        )

        unlimited_resp = client.get(
            "/study-items/lexemes",
            params={"shared_deck_id": shared_deck_id},
            headers=http_headers,
        )
        check(
            "37. GET /study-items/lexemes without limit still returns all 50 (default unchanged)",
            len(unlimited_resp.json()) == word_count,
        )

        due_only_limited_resp = client.get(
            "/study-items/lexemes",
            params={"shared_deck_id": shared_deck_id, "due_only": "true", "limit": 30},
            headers=http_headers,
        )
        check(
            "38. GET /study-items/lexemes?due_only=true&limit=30 still returns 0 "
            "(Round 1 due_only fix preserved under the new limit param)",
            due_only_limited_resp.status_code == 200 and len(due_only_limited_resp.json()) == 0,
        )

        invalid_limit_resp = client.get(
            "/study-items/lexemes",
            params={"shared_deck_id": shared_deck_id, "limit": 0},
            headers=http_headers,
        )
        check(
            "39. GET /study-items/lexemes?limit=0 is rejected (400), not silently treated as unlimited",
            invalid_limit_resp.status_code == 400,
        )

        negative_limit_resp = client.get(
            "/study-items/lexemes",
            params={"shared_deck_id": shared_deck_id, "limit": -1},
            headers=http_headers,
        )
        check(
            "39b. GET /study-items/lexemes?limit=-1 is also rejected (400)",
            negative_limit_resp.status_code == 400,
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

    # --- 2b. Owner cannot import/subscribe to their own shared deck --------
    with get_connection() as connection:
        import_count_before = connection.execute(
            "SELECT import_count FROM shared_decks WHERE id = ?", (shared_deck_id,)
        ).fetchone()["import_count"]
    owner_import_result = import_shared_deck(owner_id, shared_deck_id)
    check(
        "6b. owner cannot import their own lexeme-mode shared deck",
        owner_import_result == "forbidden",
    )
    check(
        "6c. owner self-import attempt did not create a subscription row",
        count_rows(
            "user_deck_subscriptions", "user_id = ? AND shared_deck_id = ?",
            (owner_id, shared_deck_id),
        )
        == 0,
    )
    with get_connection() as connection:
        import_count_after = connection.execute(
            "SELECT import_count FROM shared_decks WHERE id = ?", (shared_deck_id,)
        ).fetchone()["import_count"]
    check(
        "6d. owner self-import attempt did not increment import_count",
        import_count_after == import_count_before,
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

    # --- 4b. Phase 20 Round 1: due_only=true must agree with /stats' own
    # due_count definition -- a lexeme with no user_word_progress row yet is
    # "new", never "due", in both places (see lexeme_repository.py's
    # list_shared_deck_words_with_progress docstring). Before this fix,
    # due_only=true still matched progress-less rows, so subscribing to a
    # large deck (e.g. JLPT N1) flooded the due-today queue with every
    # never-reviewed word while /stats reported 0 due for the same lexemes.
    stats_before_any_review = get_subscribed_lexeme_stats_summary(importer_id)
    check(
        "8c. stats summary reports due_count=0 before any progress row exists",
        stats_before_any_review["due_count"] == 0,
    )
    check(
        "8d. stats summary reports new_count for every progress-less word",
        stats_before_any_review["new_count"] == len(words),
    )
    due_only_before_any_review = list_shared_deck_words_with_progress(
        shared_deck_id, importer_id, due_only=True
    )
    check(
        "8e. due_only=true returns zero progress-less words (matches stats due_count=0)",
        len(due_only_before_any_review) == 0,
    )
    non_due_only_overlay = list_shared_deck_words_with_progress(
        shared_deck_id, importer_id, due_only=False
    )
    check(
        "8f. due_only=false (new/unclassified path) still returns every word",
        len(non_due_only_overlay) == len(words),
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

    # Positive case for the Round 1 due_only fix: once a real progress row
    # exists with status 'unknown' and no future next_review_at, it IS due --
    # the fix narrows due_only to exclude progress-less rows, it must not
    # also start excluding genuinely-due rows that do have a progress row.
    due_only_after_status_change = list_shared_deck_words_with_progress(
        shared_deck_id, importer_id, due_only=True
    )
    check(
        "9d. due_only=true now includes the word with a real 'unknown' progress row",
        any(item["lexeme_id"] == target_lexeme_id for item in due_only_after_status_change),
    )
    check(
        "9e. due_only=true still excludes the remaining progress-less words",
        len(due_only_after_status_change) == 1,
    )

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
    owner_legacy_result = import_shared_deck(owner_id, legacy_deck_id)
    check(
        "11d. owner cannot import their own legacy shared deck",
        owner_legacy_result == "forbidden",
    )
    check(
        "11e. owner self-import attempt did not create a personal deck copy",
        count_rows("decks", "user_id = ?", (owner_id,)) == 0,
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
    run_new_lexeme_limit_checks()

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
