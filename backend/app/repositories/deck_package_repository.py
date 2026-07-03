from __future__ import annotations

import sqlite3
from typing import Any

from app.database import get_connection, now_iso, row_to_dict
from app.schemas import DeckPackage


def get_unique_imported_deck_name(
    connection: sqlite3.Connection, user_id: int, original_name: str
) -> str:
    base_name = original_name.strip() or "가져온 덱"
    existing_names = {
        row["name"]
        for row in connection.execute(
            "SELECT name FROM decks WHERE user_id = ?", (user_id,)
        ).fetchall()
    }
    if base_name not in existing_names:
        return base_name

    first_candidate = f"{base_name} (가져옴)"
    if first_candidate not in existing_names:
        return first_candidate

    suffix = 2
    while True:
        candidate = f"{base_name} (가져옴 {suffix})"
        if candidate not in existing_names:
            return candidate
        suffix += 1


def export_deck_package(
    user_id: int, deck_id: int, include_common_terms: bool = False
) -> dict[str, Any] | None:
    with get_connection() as connection:
        deck = connection.execute(
            """
            SELECT id, name, description
            FROM decks
            WHERE id = ?
              AND user_id = ?
            """,
            (deck_id, user_id),
        ).fetchone()
        if not deck:
            return None

        vocab_rows = connection.execute(
            """
            SELECT surface, base_form, reading, part_of_speech, normalized_form,
                   meaning_ko, dictionary_gloss, context_explanation_ko,
                   example_sentence, quality_tag
            FROM vocab_items
            WHERE deck_id = ?
              AND user_id = ?
            ORDER BY created_at ASC, id ASC
            """,
            (deck_id, user_id),
        ).fetchall()

        term_params: tuple[Any, ...] = (user_id, deck_id)
        term_clause = "custom_terms.user_id = ? AND custom_terms.deck_id = ?"
        if include_common_terms:
            term_clause = (
                "custom_terms.user_id = ? "
                "AND (custom_terms.deck_id = ? OR custom_terms.deck_id IS NULL)"
            )

        term_rows = connection.execute(
            f"""
            SELECT term, reading, part_of_speech, meaning_ko, description
            FROM custom_terms
            WHERE {term_clause}
            ORDER BY created_at ASC, id ASC
            """,
            term_params,
        ).fetchall()

    return {
        "package_type": "jp_vocab_reader_deck",
        "package_version": 1,
        "exported_at": now_iso(),
        "app": {
            "name": "JP Vocab Reader",
            "format": "deck_package",
        },
        "deck": {
            "name": deck["name"],
            "description": deck["description"] or "",
        },
        "vocab_items": [row_to_dict(row) for row in vocab_rows],
        "custom_terms": [row_to_dict(row) for row in term_rows],
    }


def dump_model(model: Any) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


def import_deck_package(user_id: int, package: DeckPackage) -> dict[str, Any]:
    timestamp = now_iso()
    deck_payload = dump_model(package.deck)
    vocab_payloads = [dump_model(item) for item in package.vocab_items]
    custom_term_payloads = [dump_model(term) for term in package.custom_terms]

    imported_vocab_count = 0
    skipped_vocab_count = 0
    imported_custom_term_count = 0
    skipped_custom_term_count = 0
    seen_vocab_keys: set[tuple[str, str]] = set()
    seen_custom_terms: set[str] = set()

    with get_connection() as connection:
        deck_name = get_unique_imported_deck_name(
            connection, user_id, str(deck_payload.get("name") or "")
        )
        deck_description = str(deck_payload.get("description") or "").strip()
        cursor = connection.execute(
            """
            INSERT INTO decks (user_id, name, description, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, deck_name, deck_description, timestamp, timestamp),
        )
        deck_id = int(cursor.lastrowid)

        for raw_item in vocab_payloads:
            values = {
                key: value.strip() if isinstance(value, str) else value
                for key, value in raw_item.items()
            }
            surface = str(values.get("surface") or "").strip()
            base_form = str(values.get("base_form") or "").strip() or surface
            reading = str(values.get("reading") or "").strip()
            if not surface and not base_form:
                skipped_vocab_count += 1
                continue

            key = (base_form, reading)
            if key in seen_vocab_keys:
                skipped_vocab_count += 1
                continue
            seen_vocab_keys.add(key)

            normalized_form = (
                str(values.get("normalized_form") or "").strip() or base_form
            )
            connection.execute(
                """
                INSERT INTO vocab_items (
                    user_id, deck_id, surface, base_form, reading, part_of_speech,
                    normalized_form, meaning_ko, dictionary_gloss, quality_tag,
                    context_explanation_ko, example_sentence, status,
                    correct_count, wrong_count, last_reviewed_at, review_level,
                    next_review_at, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'unknown', 0, 0, NULL, 0, NULL, ?, ?)
                """,
                (
                    user_id,
                    deck_id,
                    surface or base_form,
                    base_form,
                    reading,
                    str(values.get("part_of_speech") or "").strip(),
                    normalized_form,
                    str(values.get("meaning_ko") or "").strip(),
                    str(values.get("dictionary_gloss") or "").strip(),
                    str(values.get("quality_tag") or "").strip() or "normal",
                    str(values.get("context_explanation_ko") or "").strip(),
                    str(values.get("example_sentence") or "").strip(),
                    timestamp,
                    timestamp,
                ),
            )
            imported_vocab_count += 1

        for raw_term in custom_term_payloads:
            values = {
                key: value.strip() if isinstance(value, str) else value
                for key, value in raw_term.items()
            }
            term = str(values.get("term") or "").strip()
            if not term:
                skipped_custom_term_count += 1
                continue
            if term in seen_custom_terms:
                skipped_custom_term_count += 1
                continue
            seen_custom_terms.add(term)

            connection.execute(
                """
                INSERT INTO custom_terms (
                    user_id, term, reading, part_of_speech, meaning_ko, description,
                    deck_id, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    term,
                    str(values.get("reading") or "").strip(),
                    str(values.get("part_of_speech") or "").strip() or "명사",
                    str(values.get("meaning_ko") or "").strip(),
                    str(values.get("description") or "").strip(),
                    deck_id,
                    timestamp,
                    timestamp,
                ),
            )
            imported_custom_term_count += 1

    return {
        "deck_id": deck_id,
        "deck_name": deck_name,
        "imported_vocab_count": imported_vocab_count,
        "skipped_vocab_count": skipped_vocab_count,
        "imported_custom_term_count": imported_custom_term_count,
        "skipped_custom_term_count": skipped_custom_term_count,
        "message": "덱 패키지를 가져왔습니다.",
    }
