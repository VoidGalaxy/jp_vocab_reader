"""Manual benchmark for lexeme study-queue queries against large shared decks.

Not a CI smoke test: no PASS/FAIL assertions, just timing numbers. Runs
entirely against a throwaway SQLite file (never backend/vocab.db, never
whatever DATABASE_URL is already set in the environment, never Neon) so it's
safe to run anywhere. Loads the three real JLPT recommended-vocabulary
packages (N1/N2/N3, ~7,100 words combined) into a scratch DB to measure
list_subscribed_lexeme_study_items / list_shared_deck_words_with_progress /
get_subscribed_lexeme_stats_summary at realistic large-deck scale -- see
docs/architecture/shared-lexeme-progress-storage.md for the Phase 20-22
work this follows up on (due_only definition, SQL LIMIT pushdown,
exclude_known pushdown).

Usage:
    cd backend
    .venv\\Scripts\\Activate.ps1   (or source .venv/bin/activate)
    python scripts/benchmark_lexeme_study_queue.py
"""

from __future__ import annotations

import json
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Callable

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Must happen before any `app.*` import touches app.settings/app.database, since
# get_database_url() is read at connection time -- this makes every
# get_connection() call in this process use the scratch file, never the
# developer's real backend/vocab.db or a Neon DATABASE_URL left in .env.
_SCRATCH_DB = Path(tempfile.gettempdir()) / "jp_vocab_reader_benchmark_lexeme_study_queue.db"
_SCRATCH_SIDECARS = [
    _SCRATCH_DB.with_name(_SCRATCH_DB.name + suffix)
    for suffix in ("-wal", "-shm", "-journal")
]


def _remove_scratch_files() -> None:
    _SCRATCH_DB.unlink(missing_ok=True)
    for sidecar in _SCRATCH_SIDECARS:
        sidecar.unlink(missing_ok=True)


_remove_scratch_files()
_SCRATCH_DATABASE_URL = f"sqlite:///{_SCRATCH_DB.as_posix()}"

# Belt-and-suspenders check on the URL this script itself just built --
# refuses to proceed if it's somehow not a plain local sqlite:/// URL, or
# mentions Neon's host, before any app module (and therefore any DB
# connection) is even imported.
if "neon.tech" in _SCRATCH_DATABASE_URL:
    raise RuntimeError(
        "refusing to start: scratch DATABASE_URL must never contain neon.tech"
    )
if not _SCRATCH_DATABASE_URL.startswith("sqlite:///"):
    raise RuntimeError(
        "refusing to start: scratch DATABASE_URL must be a local sqlite:/// URL"
    )

os.environ["DATABASE_URL"] = _SCRATCH_DATABASE_URL

from app.database import get_connection, init_db, now_iso  # noqa: E402
from app.repositories.lexeme_repository import (  # noqa: E402
    get_subscribed_lexeme_stats_summary,
    list_shared_deck_words_with_progress,
    list_subscribed_lexeme_study_items,
)
from app.repositories.shared_deck_repository import import_shared_deck  # noqa: E402
from app.schemas import DeckPackage  # noqa: E402

DATA_DIR = BACKEND_DIR / "data" / "jlpt" / "packages"
PACKAGES = [
    ("N1", DATA_DIR / "jlpt_n1_recommended_deck.json"),
    ("N2", DATA_DIR / "jlpt_n2_recommended_deck.json"),
    ("N3", DATA_DIR / "jlpt_n3_recommended_deck.json"),
]
KNOWN_FRACTION = 0.15
REPEAT_COUNT = 5


def create_user(connection: Any, email: str, display_name: str) -> int:
    timestamp = now_iso()
    cursor = connection.execute(
        """
        INSERT INTO users (email, display_name, auth_provider, created_at, updated_at)
        VALUES (?, ?, 'local', ?, ?)
        """,
        (email, display_name, timestamp, timestamp),
    )
    return int(cursor.lastrowid)


def create_shared_deck(connection: Any, owner_user_id: int, title: str, description: str) -> int:
    timestamp = now_iso()
    cursor = connection.execute(
        """
        INSERT INTO shared_decks (
            owner_user_id, title, description, visibility,
            vocab_count, custom_term_count, import_count, created_at, updated_at
        )
        VALUES (?, ?, ?, 'public', 0, 0, 0, ?, ?)
        """,
        (owner_user_id, title, description, timestamp, timestamp),
    )
    return int(cursor.lastrowid)


# Reimplemented locally (not imported from seed_jlpt_shared_decks.py, which
# is a CLI entry point with its own argument parsing / stdout side effects
# that don't belong in a benchmark run) -- mirrors that script's
# upsert_seed_lexeme/add_seed_word_to_shared_deck helpers, but reuses a
# single connection across the whole package load instead of opening one per
# row, so loading ~7,100 words doesn't spend most of its time on SQLite
# connection setup.
def upsert_seed_lexeme(
    connection: Any,
    *,
    surface: str,
    base_form: str,
    reading: str,
    part_of_speech: str,
    meaning_ko: str,
    dictionary_gloss: str,
    jlpt_level: str,
) -> int:
    timestamp = now_iso()
    base_form = (base_form or surface or "").strip() or surface.strip()
    surface = surface.strip() or base_form
    reading = (reading or "").strip()
    part_of_speech = (part_of_speech or "").strip()
    existing = connection.execute(
        """
        SELECT id FROM lexemes
        WHERE base_form = ? AND reading = ? AND part_of_speech = ?
        """,
        (base_form, reading, part_of_speech),
    ).fetchone()
    if existing:
        lexeme_id = int(existing["id"])
        connection.execute(
            """
            UPDATE lexemes
            SET surface = ?, meaning_ko = ?, dictionary_gloss = ?,
                jlpt_level = COALESCE(?, jlpt_level), updated_at = ?
            WHERE id = ?
            """,
            (surface, meaning_ko.strip(), dictionary_gloss.strip(), jlpt_level, timestamp, lexeme_id),
        )
        return lexeme_id

    cursor = connection.execute(
        """
        INSERT INTO lexemes (
            surface, base_form, reading, part_of_speech, meaning_ko,
            dictionary_gloss, jlpt_level, source_type, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, 'jlpt', ?, ?)
        """,
        (
            surface, base_form, reading, part_of_speech,
            meaning_ko.strip(), dictionary_gloss.strip(), jlpt_level,
            timestamp, timestamp,
        ),
    )
    return int(cursor.lastrowid)


def add_seed_word_to_shared_deck(
    connection: Any, shared_deck_id: int, lexeme_id: int, sort_order: int
) -> None:
    timestamp = now_iso()
    connection.execute(
        """
        INSERT INTO shared_deck_words (
            shared_deck_id, lexeme_id, sort_order, created_at,
            display_meaning_ko, example_sentence, context_explanation_ko,
            tags_json, published_note
        )
        VALUES (?, ?, ?, ?, NULL, NULL, NULL, NULL, NULL)
        ON CONFLICT (shared_deck_id, lexeme_id) DO UPDATE SET
            sort_order = excluded.sort_order
        """,
        (shared_deck_id, lexeme_id, sort_order, timestamp),
    )


def load_package(path: Path) -> DeckPackage:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return DeckPackage(**raw)


def load_deck_fixture(
    connection: Any, owner_user_id: int, level: str, path: Path
) -> dict[str, Any]:
    package = load_package(path)
    title = f"[benchmark] {package.deck.name}"
    shared_deck_id = create_shared_deck(connection, owner_user_id, title, package.deck.description)
    lexeme_ids: list[int] = []
    for sort_order, item in enumerate(package.vocab_items):
        base_form = (item.base_form or item.surface or "").strip()
        if not base_form:
            continue
        lexeme_id = upsert_seed_lexeme(
            connection,
            surface=item.surface or base_form,
            base_form=base_form,
            reading=item.reading,
            part_of_speech=item.part_of_speech,
            meaning_ko=item.meaning_ko,
            dictionary_gloss=item.dictionary_gloss,
            jlpt_level=level,
        )
        add_seed_word_to_shared_deck(connection, shared_deck_id, lexeme_id, sort_order)
        lexeme_ids.append(lexeme_id)
    connection.execute(
        "UPDATE shared_decks SET vocab_count = ?, updated_at = ? WHERE id = ?",
        (len(lexeme_ids), now_iso(), shared_deck_id),
    )
    return {
        "level": level,
        "shared_deck_id": shared_deck_id,
        "title": title,
        "count": len(lexeme_ids),
        "lexeme_ids": lexeme_ids,
    }


def mark_known(connection: Any, user_id: int, lexeme_ids: list[int]) -> int:
    """Directly inserts user_word_progress rows with status='known' for the
    given lexemes -- a raw INSERT (single reused connection), not
    update_word_status(), for the same "don't pay per-row connection setup
    on a few hundred rows" reason as the fixture loader above. Semantically
    equivalent to what update_word_status(user_id, lexeme_id, "known") would
    produce for a lexeme with no prior progress row.
    """
    timestamp = now_iso()
    marked = 0
    for lexeme_id in lexeme_ids:
        connection.execute(
            """
            INSERT INTO user_word_progress (
                user_id, lexeme_id, status, review_level, correct_count,
                wrong_count, created_at, updated_at
            )
            VALUES (?, ?, 'known', 0, 0, 0, ?, ?)
            """,
            (user_id, lexeme_id, timestamp, timestamp),
        )
        marked += 1
    return marked


def time_scenario(
    label: str, fn: Callable[[], Any], repeat: int = REPEAT_COUNT
) -> dict[str, Any]:
    fn()  # warm-up, discarded (page cache / query-plan warmup, not measured)
    durations_ms: list[float] = []
    last_result: Any = None
    for _ in range(repeat):
        start = time.perf_counter()
        last_result = fn()
        durations_ms.append((time.perf_counter() - start) * 1000)

    if isinstance(last_result, dict):
        returned_count: Any = last_result
    else:
        returned_count = len(last_result)

    return {
        "label": label,
        "returned_count": returned_count,
        "min_ms": min(durations_ms),
        "median_ms": statistics.median(durations_ms),
    }


def simulate_pre_phase24_all_mode(
    subscriber_id: int, deck_ids: list[int], limit: int
) -> list[int]:
    """Re-implements the pre-Phase-24 all-mode algorithm by hand: fetch each
    subscribed deck in full (limit=None), dedup by lexeme_id in Python, then
    slice to `limit` -- exactly what list_subscribed_lexeme_study_items()
    did before this round capped each deck's SQL fetch at `limit`. Kept
    side by side with the real (now-capped) call below so this benchmark
    shows the actual before/after cost on the same data in the same run,
    not just a one-time number from an earlier phase.
    """
    seen: set[int] = set()
    sequence: list[int] = []
    for deck_id in sorted(deck_ids):
        words = list_shared_deck_words_with_progress(
            deck_id, subscriber_id, due_only=False, limit=None, exclude_known=True
        )
        for word in words:
            lexeme_id = word["lexeme_id"]
            if lexeme_id in seen:
                continue
            seen.add(lexeme_id)
            sequence.append(lexeme_id)
    return sequence[:limit]


def print_scenarios_table(rows: list[dict[str, Any]]) -> None:
    header = f"{'scenario':<55} {'returned_count':<20} {'min_ms':>10} {'median_ms':>10}"
    print(header)
    print("-" * len(header))
    for row in rows:
        returned = row["returned_count"]
        returned_display = str(returned) if not isinstance(returned, dict) else json.dumps(returned, ensure_ascii=False)
        print(
            f"{row['label']:<55} {returned_display:<20} {row['min_ms']:>10.3f} {row['median_ms']:>10.3f}"
        )


def main() -> int:
    init_db()

    with get_connection() as connection:
        owner_id = create_user(connection, "benchmark-owner@bench.test", "Benchmark Owner")
        subscriber_id = create_user(
            connection, "benchmark-subscriber@bench.test", "Benchmark Subscriber"
        )

        decks: list[dict[str, Any]] = []
        for level, path in PACKAGES:
            if not path.exists():
                raise RuntimeError(f"missing package fixture: {path}")
            decks.append(load_deck_fixture(connection, owner_id, level, path))

        deck_by_level = {deck["level"]: deck for deck in decks}
        n1 = deck_by_level["N1"]
        known_lexeme_ids = n1["lexeme_ids"][: int(len(n1["lexeme_ids"]) * KNOWN_FRACTION)]
        known_marked = mark_known(connection, subscriber_id, known_lexeme_ids)

    for deck in decks:
        result = import_shared_deck(subscriber_id, deck["shared_deck_id"])
        if not isinstance(result, dict) or result.get("mode") != "subscribed":
            raise RuntimeError(f"unexpected import result for {deck['title']!r}: {result!r}")

    print("=== fixture summary ===")
    for deck in decks:
        print(
            f"  {deck['level']}: shared_deck_id={deck['shared_deck_id']} "
            f"title={deck['title']!r} count={deck['count']}"
        )
    print(f"  known-marked on N1: {known_marked} of {n1['count']} ({KNOWN_FRACTION:.0%})")
    print()

    n1_id = n1["shared_deck_id"]
    scenarios = [
        time_scenario(
            "single N1, study-queue, limit=30, due_only=false",
            lambda: list_subscribed_lexeme_study_items(
                subscriber_id, shared_deck_id=n1_id, limit=30
            ),
        ),
        time_scenario(
            "single N1, study-queue, limit=None, due_only=false",
            lambda: list_subscribed_lexeme_study_items(
                subscriber_id, shared_deck_id=n1_id
            ),
        ),
        time_scenario(
            "single N1, raw detail-view (exclude_known=false), limit=30 -- "
            "known words sorted first still fill the page (pre-Phase22 shape)",
            lambda: list_shared_deck_words_with_progress(
                n1_id, subscriber_id, due_only=False, limit=30, exclude_known=False
            ),
        ),
        time_scenario(
            "all N1+N2+N3, study-queue, limit=30 (pre-Phase24 full-scan simulation)",
            lambda: simulate_pre_phase24_all_mode(
                subscriber_id, [deck["shared_deck_id"] for deck in decks], 30
            ),
        ),
        time_scenario(
            "all N1+N2+N3, study-queue, limit=30 (Phase24 per-deck SQL LIMIT cap)",
            lambda: list_subscribed_lexeme_study_items(subscriber_id, limit=30),
        ),
        time_scenario(
            "single N1, study-queue, due_only=true, limit=30",
            lambda: list_subscribed_lexeme_study_items(
                subscriber_id, shared_deck_id=n1_id, due_only=True, limit=30
            ),
        ),
        time_scenario(
            "get_subscribed_lexeme_stats_summary(subscriber)",
            lambda: get_subscribed_lexeme_stats_summary(subscriber_id),
        ),
    ]

    print("=== scenarios ===")
    print_scenarios_table(scenarios)

    # Extra, non-assertive detail: confirm the Phase 24 capped call and the
    # pre-Phase24 full-scan simulation return the *same* items on this data,
    # not just similar timings -- the speedup shown in the table above is
    # free (same result), not a tradeoff.
    old_sequence = simulate_pre_phase24_all_mode(
        subscriber_id, [deck["shared_deck_id"] for deck in decks], 30
    )
    new_sequence = [
        item["lexeme_id"]
        for item in list_subscribed_lexeme_study_items(subscriber_id, limit=30)
    ]
    print()
    print(
        "note: pre-Phase24 simulation and Phase24-capped call return "
        f"{'identical' if old_sequence == new_sequence else 'DIFFERENT'} "
        f"item sequences ({len(old_sequence)} vs {len(new_sequence)} items)"
    )

    # Extra, non-assertive detail for the raw detail-view scenario: how many
    # of its 30 returned rows are 'known' -- illustrates why
    # list_subscribed_lexeme_study_items pushes exclude_known into SQL
    # (Phase 22 Round 1) instead of relying on this raw call + a post-filter.
    raw_detail_rows = list_shared_deck_words_with_progress(
        n1_id, subscriber_id, due_only=False, limit=30, exclude_known=False
    )
    known_in_raw_page = sum(1 for row in raw_detail_rows if row.get("status") == "known")
    print()
    print(
        f"note: raw detail-view limit=30 page contains {known_in_raw_page}/30 'known' rows "
        "(illustrates the bug Phase 22 Round 1 fixed for the study-queue path)"
    )

    return 0


if __name__ == "__main__":
    exit_code = 1
    try:
        exit_code = main()
    finally:
        _remove_scratch_files()
        print()
        print(f"scratch DB cleaned up: {_SCRATCH_DB} (+ -wal/-shm/-journal sidecars)")
    sys.exit(exit_code)
