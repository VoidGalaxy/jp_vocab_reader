"""Additive SRS storage for SQLite and PostgreSQL (Gate B-1).

Only adds nullable/defaulted columns, new tables and indexes. It never
rewrites, backfills or deletes existing rows: every existing card keeps its
status, review_level, next_review_at and counters, and stays srs_engine =
'legacy'. srs_participation stays NULL ("not migrated") -- in particular the
schema does NOT move legacy `known` cards to paused; that is an explicit,
reviewed migration step in a later gate. Nothing here replays history or
turns the FSRS engine on.

Card columns are added to both card tables:
  vocab_items          personal card  (user_id, vocab_item id)
  user_word_progress   subscribed card (user_id, lexeme_id)
Review-log columns are added to both log tables (review_logs,
lexeme_review_logs); one log row still means exactly one rating.

There is deliberately no intake reservation table: the approved first step
is a daily new goal (S1), and reservations/claims (S2) are a separate,
later approval.
"""

from __future__ import annotations

import re
from typing import Any


class SchemaUpgradeError(RuntimeError):
    """A schema upgrade found a database shape it is not approved to change. The caller's
    schema transaction rolls back, so nothing is changed."""

CARD_TABLES = ("vocab_items", "user_word_progress")
LOG_TABLES = ("review_logs", "lexeme_review_logs")

ENGINE_VALUES = ("legacy", "fsrs")
PARTICIPATION_VALUES = ("active", "paused")
HISTORY_QUALITY_VALUES = ("complete", "incomplete", "fresh")
SRS_MODE_VALUES = ("legacy", "shadow", "fsrs")
DAILY_NEW_GOAL_DEFAULT = 20
DAILY_NEW_GOAL_MAX = 500


def _in_list(column: str, values: tuple[str, ...]) -> str:
    quoted = ", ".join(f"'{value}'" for value in values)
    return f"CHECK ({column} IS NULL OR {column} IN ({quoted}))"


def card_columns(is_postgres: bool) -> list[str]:
    real = "DOUBLE PRECISION" if is_postgres else "REAL"
    return [
        f"srs_engine TEXT NOT NULL DEFAULT 'legacy' CHECK (srs_engine IN ('legacy', 'fsrs'))",
        "srs_config_version TEXT",
        # 1 Learning, 2 Review, 3 Relearning (fsrs.State values). NULL = unreviewed / not FSRS.
        "srs_state INTEGER CHECK (srs_state IS NULL OR srs_state IN (1, 2, 3))",
        "srs_step INTEGER CHECK (srs_step IS NULL OR srs_step >= 0)",
        f"srs_stability {real}",
        f"srs_difficulty {real}",
        # FSRS-computed due vs. the due actually used for queueing (may keep
        # a protected legacy due after migration). UTC ISO text like next_review_at.
        "srs_due_at TEXT",
        "srs_effective_due_at TEXT",
        "srs_last_review_at TEXT",
        "srs_card_version INTEGER NOT NULL DEFAULT 0",
        f"srs_participation TEXT {_in_list('srs_participation', PARTICIPATION_VALUES)}",
        "srs_pause_reason TEXT",
        f"srs_history_quality TEXT {_in_list('srs_history_quality', HISTORY_QUALITY_VALUES)}",
        # Suspicion markers such as short_interval_repeat. Never decide quality by themselves.
        "srs_history_flags TEXT",
        "completion_metric_version TEXT",
        "first_completed_at TEXT",
        # Gate D-2 U11 B: source of first_completed_at (a metric version, or
        # source_missing / source_unknown), and the first completion under the current
        # metric as a (time, version) pair -- both NULL or both set.
        "first_completed_source TEXT",
        "version_first_completed_at TEXT",
        "version_first_completed_version TEXT CHECK ((version_first_completed_at IS NULL) = "
        "(version_first_completed_version IS NULL))",
        # Gate D-2 U4 (D-H7): past-learning mark, written once by the explicit
        # migration apply path (app/srs/history_intro.py). Not engine state: the
        # rollback excludes these columns by name (migration.ROLLBACK_PRESERVED).
        "history_intro_status TEXT CHECK (history_intro_status IS NULL OR "
        "history_intro_status IN ('logged', 'before_tracking', 'unknown'))",
        "history_intro_known_by TEXT",
        # Gate D-2 U7 (D-H4): id of the card's first real FSRS review log after a U5
        # incomplete-history conversion. Completion evidence starts there. Written once
        # in that review's transaction; never restored by a rollback (ROLLBACK_PRESERVED).
        "evidence_from_log_id INTEGER",
    ]


DELETION_EVIDENCE_COLUMNS = [
    "history_intro_status TEXT CHECK (history_intro_status IS NULL OR "
    "history_intro_status IN ('logged', 'before_tracking', 'unknown'))",
    "history_intro_known_by TEXT",
]

LOG_COLUMNS = [
    "request_id TEXT",
    "srs_engine TEXT",
    "srs_config_version TEXT",
    "card_version_before INTEGER",
    # Audit/rollback snapshots (engine.state_to_json); never the authoritative state.
    "srs_before_json TEXT",
    "srs_after_json TEXT",
    "seoul_date TEXT",
    "is_first_review INTEGER",
]


# P-RB review fix 1: an active row always carries its own account as the marker (NOT NULL:
# `NULL = user_id` is unknown, which a CHECK lets pass); a released row never does.
BLOCK_STATE_CHECK = ("((status = 'active' AND active_user_id IS NOT NULL AND active_user_id = user_id "
                     "AND released_at IS NULL AND release_reason IS NULL) "
                     "OR (status = 'released' AND active_user_id IS NULL AND released_at IS NOT NULL "
                     "AND release_reason IS NOT NULL))")
RECOVERY_STATE_CHECK = ("((state <> 'closed' AND active_user_id IS NOT NULL AND active_user_id = user_id "
                        "AND closed_at IS NULL AND close_reason IS NULL) "
                        "OR (state = 'closed' AND active_user_id IS NULL AND closed_at IS NOT NULL "
                        "AND close_reason IS NOT NULL))")
_BLOCK_COLUMNS = ("id, user_id, purpose, recovery_key, grant_hash, status, active_user_id, run_watermark, "
                  "changes_started, created_at, changes_started_at, released_at, release_reason")


def _new_tables(is_postgres: bool) -> list[str]:
    pk = "INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY" if is_postgres else "INTEGER PRIMARY KEY AUTOINCREMENT"
    user_fk = "REFERENCES users(id) ON DELETE CASCADE"
    return [
        f"""
        CREATE TABLE IF NOT EXISTS srs_config_versions (
            config_version TEXT PRIMARY KEY,
            engine TEXT NOT NULL,
            library_version TEXT NOT NULL,
            adapter_version TEXT NOT NULL,
            config_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS srs_user_settings (
            user_id INTEGER PRIMARY KEY {user_fk},
            srs_mode TEXT NOT NULL DEFAULT 'legacy' {_in_list('srs_mode', SRS_MODE_VALUES)},
            config_version TEXT,
            daily_new_goal INTEGER NOT NULL DEFAULT {DAILY_NEW_GOAL_DEFAULT}
                CHECK (daily_new_goal >= 0 AND daily_new_goal <= {DAILY_NEW_GOAL_MAX}),
            settings_version INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS srs_review_receipts (
            id {pk},
            user_id INTEGER NOT NULL {user_fk},
            request_id TEXT NOT NULL,
            card_kind TEXT NOT NULL CHECK (card_kind IN ('personal', 'lexeme')),
            card_ref INTEGER NOT NULL,
            request_hash TEXT NOT NULL,
            response_json TEXT NOT NULL,
            review_log_id INTEGER,
            created_at TEXT NOT NULL,
            UNIQUE(user_id, request_id)
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS srs_migration_runs (
            id {pk},
            run_key TEXT NOT NULL UNIQUE,
            mode TEXT NOT NULL CHECK (mode IN ('dry_run', 'apply', 'rollback')),
            status TEXT NOT NULL CHECK (status IN ('started', 'completed', 'failed', 'aborted')),
            scope_json TEXT NOT NULL,
            engine TEXT NOT NULL,
            library_version TEXT NOT NULL,
            config_version TEXT NOT NULL,
            summary_json TEXT,
            started_at TEXT NOT NULL,
            finished_at TEXT
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS srs_migration_snapshots (
            id {pk},
            run_id INTEGER NOT NULL REFERENCES srs_migration_runs(id),
            user_id INTEGER NOT NULL,
            card_kind TEXT NOT NULL CHECK (card_kind IN ('personal', 'lexeme')),
            card_ref INTEGER NOT NULL,
            card_version_before INTEGER NOT NULL,
            legacy_json TEXT NOT NULL,
            srs_before_json TEXT,
            srs_after_json TEXT,
            history_quality TEXT {_in_list('history_quality', HISTORY_QUALITY_VALUES)},
            history_flags TEXT,
            created_at TEXT NOT NULL,
            UNIQUE(run_id, card_kind, card_ref)
        )
        """,
        # Gate D-2 U3: content-free deletion ledger. Kind, account, id and time only --
        # never surface, meaning or examples. user_id is nullable only because two
        # unused legacy delete helpers may meet pre-account rows without an owner.
        f"""
        CREATE TABLE IF NOT EXISTS srs_card_deletions (
            id {pk},
            card_kind TEXT NOT NULL CHECK (card_kind IN ('personal')),
            user_id INTEGER {user_fk},
            card_ref INTEGER NOT NULL,
            deleted_at TEXT NOT NULL
        )
        """,
        # Gate D-2 U3: ids whose stored history may belong to more than one card
        # ("identity unknown"). Reason codes only; history is never relinked or removed.
        f"""
        CREATE TABLE IF NOT EXISTS srs_card_identity_flags (
            id {pk},
            user_id INTEGER NOT NULL {user_fk},
            card_kind TEXT NOT NULL CHECK (card_kind IN ('personal')),
            card_ref INTEGER NOT NULL,
            reasons TEXT NOT NULL,
            detected_at TEXT NOT NULL,
            UNIQUE(user_id, card_kind, card_ref)
        )
        """,
        # Gate D-2 U8 plan B: one row per evidence-window restart. The first real FSRS
        # review after a restart re-conversion replaced the card's boundary
        # (previous_boundary -> new_boundary, the review's own log) on the authority of
        # one re-conversion snapshot, used at most once. Ids and versions only.
        f"""
        CREATE TABLE IF NOT EXISTS srs_evidence_restarts (
            id {pk},
            user_id INTEGER NOT NULL {user_fk},
            card_kind TEXT NOT NULL CHECK (card_kind IN ('personal', 'lexeme')),
            card_ref INTEGER NOT NULL,
            source_snapshot_id INTEGER NOT NULL UNIQUE,
            previous_boundary INTEGER NOT NULL,
            new_boundary INTEGER NOT NULL,
            card_version_before INTEGER NOT NULL,
            created_at TEXT NOT NULL
        )
        """,
        # P-RB (P_RB_BLOCK_CONTRACT.md): one active write block per account at most
        # (active_user_id UNIQUE; NULL once released). Codes, ids, times and a token HASH
        # only. RESTRICT: an account is never removed underneath its block record.
        f"""
        CREATE TABLE IF NOT EXISTS account_write_blocks (
            id {pk},
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            purpose TEXT NOT NULL CHECK (purpose IN ('srs_recovery')),
            recovery_key TEXT NOT NULL UNIQUE,
            grant_hash TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('active', 'released')),
            active_user_id INTEGER UNIQUE,
            run_watermark INTEGER NOT NULL,
            changes_started INTEGER NOT NULL DEFAULT 0 CHECK (changes_started IN (0, 1)),
            created_at TEXT NOT NULL,
            changes_started_at TEXT,
            released_at TEXT,
            release_reason TEXT CHECK (release_reason IS NULL OR release_reason IN ('completed', 'precheck_unrecoverable')),
            CONSTRAINT account_write_blocks_active_state CHECK {BLOCK_STATE_CHECK}
        )
        """,
        # P-RB tool contract 2-1: the recovery progress record. One ACTIVE record per account
        # (active_user_id UNIQUE, NOT NULL and equal to user_id while not closed); closed
        # records are kept as history. block_id names the account's write block; it is
        # checked in code and by the audit, not by an FK, because the approved block-table
        # structure admits no inbound reference. Codes, ids, hashes and counts only.
        f"""
        CREATE TABLE IF NOT EXISTS account_recovery_runs (
            id {pk},
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            block_id INTEGER NOT NULL,
            recovery_key TEXT NOT NULL UNIQUE,
            plan_fingerprint TEXT NOT NULL,
            state TEXT NOT NULL CHECK (state IN ('prepared', 'applied', 'verified', 'closed')),
            active_user_id INTEGER UNIQUE,
            source_runs_json TEXT NOT NULL,
            baseline_json TEXT NOT NULL,
            verification_json TEXT,
            verified_digest TEXT,
            prepared_at TEXT NOT NULL,
            applied_at TEXT,
            verified_at TEXT,
            closed_at TEXT,
            close_reason TEXT CHECK (close_reason IS NULL OR close_reason IN ('precheck_unrecoverable', 'completed')),
            CONSTRAINT account_recovery_runs_active_state CHECK {RECOVERY_STATE_CHECK}
        )
        """,
    ]


INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_vocab_items_srs_queue ON vocab_items(user_id, srs_engine, srs_participation, srs_effective_due_at)",
    "CREATE INDEX IF NOT EXISTS idx_user_word_progress_srs_queue ON user_word_progress(user_id, srs_engine, srs_participation, srs_effective_due_at)",
    "CREATE INDEX IF NOT EXISTS idx_review_logs_user_item_time ON review_logs(user_id, vocab_item_id, reviewed_at, id)",
    "CREATE INDEX IF NOT EXISTS idx_lexeme_review_logs_user_lexeme_time ON lexeme_review_logs(user_id, lexeme_id, created_at, id)",
    "CREATE INDEX IF NOT EXISTS idx_srs_migration_snapshots_card ON srs_migration_snapshots(user_id, card_kind, card_ref)",
    "CREATE INDEX IF NOT EXISTS idx_srs_card_deletions_card ON srs_card_deletions(user_id, card_kind, card_ref)",
]


# ---- P-RB: approved structures of account_write_blocks ----------------------------------------
# Exactly two structures are recognized: PREVIOUS (as created before review fix 1: unnamed
# state check without the NOT NULL) and CURRENT. Anything else -- an extra column, constraint,
# index, trigger, view or reference, or a check that merely contains similar words -- is
# refused with no change (`account_write_blocks_structure_unrecognized`), never repaired.
_PREVIOUS_BLOCKS_SQLITE = """
        CREATE TABLE account_write_blocks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            purpose TEXT NOT NULL CHECK (purpose IN ('srs_recovery')),
            recovery_key TEXT NOT NULL UNIQUE,
            grant_hash TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('active', 'released')),
            active_user_id INTEGER UNIQUE,
            run_watermark INTEGER NOT NULL,
            changes_started INTEGER NOT NULL DEFAULT 0 CHECK (changes_started IN (0, 1)),
            created_at TEXT NOT NULL,
            changes_started_at TEXT,
            released_at TEXT,
            release_reason TEXT CHECK (release_reason IS NULL OR release_reason IN ('completed', 'precheck_unrecoverable')),
            CHECK ((status = 'active' AND active_user_id = user_id AND released_at IS NULL AND release_reason IS NULL)
                   OR (status = 'released' AND active_user_id IS NULL AND released_at IS NOT NULL
                       AND release_reason IS NOT NULL))
        )
        """
_BLOCK_UNIQUE_COLUMNS = (("active_user_id",), ("recovery_key",))

# PostgreSQL catalog (pg_get_constraintdef / pg_get_indexdef as PostgreSQL 18 renders them).
# NOT NULL constraint rows (contype 'n') are compared through the columns instead.
_PG_BLOCK_COLUMNS = (
    ("id", "integer", True, "d", None), ("user_id", "integer", True, "", None),
    ("purpose", "text", True, "", None), ("recovery_key", "text", True, "", None),
    ("grant_hash", "text", True, "", None), ("status", "text", True, "", None),
    ("active_user_id", "integer", False, "", None), ("run_watermark", "integer", True, "", None),
    ("changes_started", "integer", True, "", "0"), ("created_at", "text", True, "", None),
    ("changes_started_at", "text", False, "", None), ("released_at", "text", False, "", None),
    ("release_reason", "text", False, "", None),
)
_PG_BLOCK_COMMON = (
    ("account_write_blocks_active_user_id_key", "u", "UNIQUE (active_user_id)"),
    ("account_write_blocks_changes_started_check", "c", "CHECK ((changes_started = ANY (ARRAY[0, 1])))"),
    ("account_write_blocks_pkey", "p", "PRIMARY KEY (id)"),
    ("account_write_blocks_purpose_check", "c", "CHECK ((purpose = 'srs_recovery'::text))"),
    ("account_write_blocks_recovery_key_key", "u", "UNIQUE (recovery_key)"),
    ("account_write_blocks_release_reason_check", "c", "CHECK (((release_reason IS NULL) OR (release_reason = ANY "
                                                       "(ARRAY['completed'::text, 'precheck_unrecoverable'::text]))))"),
    ("account_write_blocks_status_check", "c", "CHECK ((status = ANY (ARRAY['active'::text, 'released'::text])))"),
    ("account_write_blocks_user_id_fkey", "f", "FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE RESTRICT"),
)
_PG_PREVIOUS_STATE = ("account_write_blocks_check", "c",
                      "CHECK ((((status = 'active'::text) AND (active_user_id = user_id) AND (released_at IS NULL) "
                      "AND (release_reason IS NULL)) OR ((status = 'released'::text) AND (active_user_id IS NULL) "
                      "AND (released_at IS NOT NULL) AND (release_reason IS NOT NULL))))")
_PG_CURRENT_STATE = ("account_write_blocks_active_state", "c",
                     "CHECK ((((status = 'active'::text) AND (active_user_id IS NOT NULL) AND (active_user_id = user_id) "
                     "AND (released_at IS NULL) AND (release_reason IS NULL)) OR ((status = 'released'::text) "
                     "AND (active_user_id IS NULL) AND (released_at IS NOT NULL) AND (release_reason IS NOT NULL))))")
_PG_BLOCK_INDEXES = (
    ("account_write_blocks_active_user_id_key", "CREATE UNIQUE INDEX account_write_blocks_active_user_id_key ON "
                                                "public.account_write_blocks USING btree (active_user_id)"),
    ("account_write_blocks_pkey", "CREATE UNIQUE INDEX account_write_blocks_pkey ON public.account_write_blocks "
                                  "USING btree (id)"),
    ("account_write_blocks_recovery_key_key", "CREATE UNIQUE INDEX account_write_blocks_recovery_key_key ON "
                                              "public.account_write_blocks USING btree (recovery_key)"),
)


def _normalized_sql(sql: Any) -> str:
    text = re.sub(r"\s+", " ", str(sql or "")).strip()
    text = re.sub(r"\s*([(),])\s*", r"\1", text)
    text = text.replace("CREATE TABLE IF NOT EXISTS ", "CREATE TABLE ")
    # SQLite stores a renamed table's name quoted ('CREATE TABLE "account_write_blocks"(...')
    return re.sub(r'^CREATE TABLE "account_write_blocks"\(', "CREATE TABLE account_write_blocks(", text)


def _unrecognized() -> SchemaUpgradeError:
    return SchemaUpgradeError("account_write_blocks_structure_unrecognized")


_SQLITE_ASCII_CASE = str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz")


def _sqlite_ascii_fold(value: str) -> str:
    # SQLite folds ASCII identifier letters, not arbitrary Unicode case pairs.
    return value.translate(_SQLITE_ASCII_CASE)


def _sqlite_blocks_structure(connection: Any) -> str:
    """'previous' or 'current' from the SQLite catalog; anything else raises (no change)."""
    row = connection.execute("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'account_write_blocks'").fetchone()
    current_sql = next(st for st in _new_tables(False) if "account_write_blocks" in st)
    shape = {_normalized_sql(current_sql): "current", _normalized_sql(_PREVIOUS_BLOCKS_SQLITE): "previous"}
    structure = shape.get(_normalized_sql(row["sql"] if row else None))
    if structure is None:
        raise _unrecognized()
    indexes = connection.execute("PRAGMA index_list(account_write_blocks)").fetchall()
    if any(index["origin"] != "u" or not index["unique"] or index["partial"] for index in indexes):
        raise _unrecognized()
    unique = sorted(tuple(r["name"] for r in connection.execute(
        "SELECT name FROM pragma_index_info(?) ORDER BY seqno", (index["name"],)).fetchall()) for index in indexes)
    if tuple(unique) != _BLOCK_UNIQUE_COLUMNS:
        raise _unrecognized()
    others = connection.execute(
        "SELECT type, name, tbl_name, sql FROM sqlite_master WHERE name <> 'account_write_blocks' "
        "AND type IN ('table', 'view', 'trigger', 'index')").fetchall()
    for other in others:
        owns_block = _sqlite_ascii_fold(other["tbl_name"]) == "account_write_blocks"
        if owns_block and other["type"] in ("index", "trigger"):
            if not (other["type"] == "index" and other["sql"] is None
                    and other["name"].startswith("sqlite_autoindex_")):
                raise _unrecognized()
        # Conservatively reject SQL mentioning the table, including quoted / qualified names.
        if (other["type"] in ("view", "trigger")
                and "account_write_blocks" in _sqlite_ascii_fold(str(other["sql"] or ""))):
            raise _unrecognized()
        if other["type"] == "table" and any(
                _sqlite_ascii_fold(fk["table"]) == "account_write_blocks"
                for fk in connection.execute("SELECT * FROM pragma_foreign_key_list(?)", (other["name"],)).fetchall()):
            raise _unrecognized()
    return structure


def _pg_blocks_structure(connection: Any) -> str:
    """'previous' or 'current' from the PostgreSQL catalog; anything else raises (no change)."""
    oid = "to_regclass('account_write_blocks')"
    columns = tuple((r["name"], r["type"], r["notnull"], r["identity"], r["dflt"]) for r in connection.execute(
        "SELECT a.attname AS name, format_type(a.atttypid, a.atttypmod) AS type, a.attnotnull AS notnull, "
        "a.attidentity::text AS identity, pg_get_expr(d.adbin, d.adrelid) AS dflt FROM pg_attribute a "
        "LEFT JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum "
        f"WHERE a.attrelid = {oid} AND a.attnum > 0 AND NOT a.attisdropped ORDER BY a.attnum").fetchall())
    constraints = tuple((r["name"], r["type"], r["def"]) for r in connection.execute(
        "SELECT conname AS name, contype::text AS type, pg_get_constraintdef(oid) AS def FROM pg_constraint "
        f"WHERE conrelid = {oid} AND contype <> 'n' ORDER BY conname").fetchall())
    indexes = tuple((r["name"], r["def"]) for r in connection.execute(
        "SELECT c.relname AS name, pg_get_indexdef(i.indexrelid) AS def FROM pg_index i JOIN pg_class c "
        f"ON c.oid = i.indexrelid WHERE i.indrelid = {oid} ORDER BY c.relname").fetchall())
    around = connection.execute(
        f"SELECT (SELECT count(*) FROM pg_trigger WHERE tgrelid = {oid} AND NOT tgisinternal) AS triggers, "
        f"(SELECT count(*) FROM pg_constraint WHERE confrelid = {oid} AND conrelid <> {oid}) AS inbound, "
        f"(SELECT count(*) FROM pg_rewrite WHERE ev_class = {oid}) AS rules, "
        f"(SELECT count(*) FROM pg_policy WHERE polrelid = {oid}) AS policies, "
        "(SELECT count(*) FROM pg_depend d JOIN pg_rewrite r ON d.classid = 'pg_rewrite'::regclass AND d.objid = r.oid "
        f"WHERE d.refobjid = {oid} AND r.ev_class <> {oid}) AS views").fetchone()
    if columns != _PG_BLOCK_COLUMNS or indexes != _PG_BLOCK_INDEXES or any(int(around[k]) for k in
                                                                           ("triggers", "inbound", "rules", "policies", "views")):
        raise _unrecognized()
    for structure, state in (("previous", _PG_PREVIOUS_STATE), ("current", _PG_CURRENT_STATE)):
        if constraints == tuple(sorted(_PG_BLOCK_COMMON + (state,))):
            return structure
    raise _unrecognized()


def _blocks_structure(connection: Any, is_postgres: bool) -> str:
    return _pg_blocks_structure(connection) if is_postgres else _sqlite_blocks_structure(connection)


def _tighten_block_state(connection: Any, is_postgres: bool) -> None:
    """The change itself, for the PREVIOUS structure only; the caller provides the single
    transaction and checks the result."""
    if is_postgres:
        # exactly the approved previous state check, by its catalog name -- nothing else is dropped
        connection.execute(f"ALTER TABLE account_write_blocks DROP CONSTRAINT {_PG_PREVIOUS_STATE[0]}, "
                           f"ADD CONSTRAINT {_PG_CURRENT_STATE[0]} CHECK {BLOCK_STATE_CHECK}")
        return
    create = next(statement for statement in _new_tables(False) if "account_write_blocks" in statement)
    sequence = connection.execute("SELECT seq FROM sqlite_sequence WHERE name = 'account_write_blocks'").fetchone()
    connection.execute(create.replace("CREATE TABLE IF NOT EXISTS account_write_blocks",
                                      "CREATE TABLE account_write_blocks_p_rb_upgrade"))
    # the previous structure has exactly these columns (checked), so every value is copied
    connection.execute(f"INSERT INTO account_write_blocks_p_rb_upgrade ({_BLOCK_COLUMNS}) "
                       f"SELECT {_BLOCK_COLUMNS} FROM account_write_blocks ORDER BY id")
    connection.execute("DROP TABLE account_write_blocks")
    connection.execute("ALTER TABLE account_write_blocks_p_rb_upgrade RENAME TO account_write_blocks")
    if sequence is not None:   # keep ids never reused, also past deleted rows
        connection.execute("UPDATE sqlite_sequence SET seq = MAX(seq, ?) WHERE name = 'account_write_blocks'",
                           (sequence["seq"],))


def _upgrade_account_write_blocks(connection: Any, is_postgres: bool) -> None:
    """P-RB: the PREVIOUS structure is tightened to CURRENT in one transaction (the PG schema
    transaction; a SAVEPOINT on SQLite), rows / ids / sequence / approved constraints and
    indexes kept. CURRENT: nothing to do. Anything else, or a row the new check would reject,
    stops before any change (never repaired, deleted, relinked or ignored)."""
    if _blocks_structure(connection, is_postgres) == "current":
        return
    bad = connection.execute(f"SELECT count(*) AS n FROM account_write_blocks WHERE CASE WHEN {BLOCK_STATE_CHECK} "
                             "THEN 0 ELSE 1 END = 1").fetchone()["n"]
    if int(bad):
        raise SchemaUpgradeError("account_write_blocks_rows_inconsistent")
    if is_postgres:
        _tighten_block_state(connection, True)
        if _blocks_structure(connection, True) != "current":
            raise _unrecognized()
        return
    connection.execute("SAVEPOINT p_rb_block_upgrade")
    try:
        _tighten_block_state(connection, False)
        if _blocks_structure(connection, False) != "current":
            raise _unrecognized()
    except BaseException:
        connection.execute("ROLLBACK TO SAVEPOINT p_rb_block_upgrade")
        connection.execute("RELEASE SAVEPOINT p_rb_block_upgrade")
        raise
    connection.execute("RELEASE SAVEPOINT p_rb_block_upgrade")


def _sqlite_column_names(connection: Any, table: str) -> set[str]:
    return {row["name"] for row in connection.execute(f"PRAGMA table_info({table})").fetchall()}


def ensure_srs_schema(connection: Any, is_postgres: bool) -> None:
    """Idempotent. Call after the card/log tables exist."""
    for table in CARD_TABLES:
        _add_columns(connection, table, card_columns(is_postgres), is_postgres)
    for table in LOG_TABLES:
        _add_columns(connection, table, LOG_COLUMNS, is_postgres)
    for statement in _new_tables(is_postgres):
        connection.execute(statement)
    _upgrade_account_write_blocks(connection, is_postgres)
    # Gate D-2 U4 deletion follow-up (E2): the deleted card's past-learning mark,
    # copied verbatim at deletion. Existing ledger rows stay NULL (no backfill);
    # NULL means "no mark copied", never "never studied".
    _add_columns(connection, "srs_card_deletions", DELETION_EVIDENCE_COLUMNS, is_postgres)
    for statement in INDEXES:
        if is_postgres:
            ensure_pg_index(connection, statement)
        else:
            connection.execute(statement)


# Gate E-3 follow-up (E-D13 A, approved 2026-10-19; contract INIT_LOCK_PROPOSAL.md 6):
# on PostgreSQL, run an additive column / index DDL only when the catalog shows it is
# really missing. `ADD COLUMN IF NOT EXISTS` and `CREATE INDEX IF NOT EXISTS` take
# AccessExclusive / Share table locks even when they end up doing nothing, which made every
# app start able to deadlock with reviews in flight (REPORT 12). A present object must
# match what the DDL would have built; anything else stops the upgrade (no DROP, no
# re-create, no REINDEX, no type change) and the whole schema transaction rolls back.
_PG_TYPES = {"TEXT": "text", "INTEGER": "integer", "DOUBLE PRECISION": "double precision"}
_COLUMN_DEFINITION = re.compile(r"^(\w+)\s+(TEXT|INTEGER|DOUBLE PRECISION)\b")
_INDEX_STATEMENT = re.compile(
    r"^\s*CREATE\s+(UNIQUE\s+)?INDEX\s+IF\s+NOT\s+EXISTS\s+(\w+)\s+ON\s+(\w+)\s*\(([\w\s,]+)\)\s*$", re.I)


def _expected_column(definition: str) -> tuple[str, str, bool]:
    match = _COLUMN_DEFINITION.match(definition)
    if match is None:
        raise SchemaUpgradeError(f"unsupported_column_definition: {definition.split(maxsplit=1)[0]}")
    return match.group(1), _PG_TYPES[match.group(2)], " NOT NULL" in f" {definition.upper()}"


def _pg_table_present(connection: Any, table: str) -> None:
    if connection.execute("SELECT to_regclass(?) IS NOT NULL AS present", (table,)).fetchone()["present"] is not True:
        raise SchemaUpgradeError(f"table_missing: {table}")


def _pg_columns(connection: Any, table: str) -> dict[str, tuple[str, bool]]:
    _pg_table_present(connection, table)
    rows = connection.execute(
        "SELECT a.attname::text AS name, format_type(a.atttypid, a.atttypmod) AS type, a.attnotnull AS not_null "
        "FROM pg_attribute a WHERE a.attrelid = to_regclass(?) AND a.attnum > 0 AND NOT a.attisdropped",
        (table,),
    ).fetchall()
    return {row["name"]: (row["type"], bool(row["not_null"])) for row in rows}


def _missing_pg_columns(connection: Any, table: str, definitions: list[str]) -> list[str]:
    present = _pg_columns(connection, table)
    missing = []
    for definition in definitions:
        name, pg_type, not_null = _expected_column(definition)
        if name not in present:
            missing.append(definition)
        elif present[name] != (pg_type, not_null):
            raise SchemaUpgradeError(f"column_definition_mismatch: {table}.{name}")
    return missing


def ensure_pg_columns(connection: Any, table: str, definitions: list[str]) -> list[str]:
    """Add only the columns that are really missing, with their existing definitions, in one
    statement; returns the names added. Present columns must have the expected type and NOT
    NULL flag (defaults / CHECKs are not compared, as ADD COLUMN IF NOT EXISTS never did)."""
    missing = _missing_pg_columns(connection, table, definitions)
    if not missing:
        return []
    clauses = ",\n".join(f"ADD COLUMN IF NOT EXISTS {definition}" for definition in missing)
    connection.execute(f"ALTER TABLE {table}\n{clauses}")
    if _missing_pg_columns(connection, table, definitions):
        raise SchemaUpgradeError(f"columns_still_missing: {table}")
    return [definition.split(maxsplit=1)[0] for definition in missing]


_PG_INDEX_STATE_SQL = """
SELECT i.relkind::text AS kind, ix.indrelid = to_regclass(?) AS on_target, ix.indisvalid AS valid,
       ix.indisready AS ready, ix.indisunique AS is_unique, ix.indexprs IS NULL AS no_expressions,
       ix.indpred IS NULL AS no_predicate, am.amname::text AS method,
       ix.indnkeyatts AS key_count, ix.indnatts AS attribute_count,
       COALESCE(keys.default_order, FALSE) AS default_order,
       COALESCE(keys.default_opclasses, FALSE) AS default_opclasses,
       COALESCE(keys.column_collations, FALSE) AS column_collations,
       (SELECT array_agg(a.attname::text ORDER BY k.n) FROM unnest(ix.indkey) WITH ORDINALITY AS k(attnum, n)
          LEFT JOIN pg_attribute a ON a.attrelid = ix.indrelid AND a.attnum = k.attnum) AS columns
FROM pg_class i
LEFT JOIN pg_index ix ON ix.indexrelid = i.oid
LEFT JOIN pg_am am ON am.oid = i.relam
LEFT JOIN LATERAL (
    SELECT bool_and(k.sort_option = 0) AS default_order,
           bool_and(op.opcdefault AND op.opcmethod = i.relam AND op.opcintype = a.atttypid) AS default_opclasses,
           bool_and(k.collation_oid = a.attcollation) AS column_collations
    FROM unnest(ix.indkey::smallint[], ix.indclass::oid[], ix.indcollation::oid[], ix.indoption::smallint[])
         WITH ORDINALITY AS k(attnum, opclass_oid, collation_oid, sort_option, n)
    LEFT JOIN pg_attribute a ON a.attrelid = ix.indrelid AND a.attnum = k.attnum
    LEFT JOIN pg_opclass op ON op.oid = k.opclass_oid
    WHERE k.n <= ix.indnkeyatts
) keys ON TRUE
WHERE i.relname = ? AND i.relnamespace = (SELECT relnamespace FROM pg_class WHERE oid = to_regclass(?))
"""


def _pg_index_state(connection: Any, name: str, table: str, columns: list[str], unique: bool) -> str:
    """"absent", "ok", or raises: the name must be this table's valid, ready btree index on
    exactly these search keys, without INCLUDE columns, using the DDL's default key options."""
    _pg_table_present(connection, table)
    rows = connection.execute(_PG_INDEX_STATE_SQL, (table, name, table)).fetchall()
    if not rows:
        return "absent"
    row = rows[0]
    if row["kind"] not in ("i", "I"):
        raise SchemaUpgradeError(f"index_name_taken_by_another_relation: {name}")
    if row["on_target"] is not True:
        raise SchemaUpgradeError(f"index_on_another_table: {name}")
    if row["valid"] is not True or row["ready"] is not True:
        raise SchemaUpgradeError(f"index_invalid: {name}")
    if (bool(row["is_unique"]) != unique or row["no_expressions"] is not True or row["no_predicate"] is not True
            or row["method"] != "btree" or list(row["columns"] or []) != columns
            or row["key_count"] != len(columns) or row["attribute_count"] != len(columns)
            or row["default_order"] is not True or row["default_opclasses"] is not True
            or row["column_collations"] is not True):
        raise SchemaUpgradeError(f"index_definition_mismatch: {name}")
    return "ok"


def ensure_pg_index(connection: Any, statement: str) -> bool:
    """Run `statement` (CREATE [UNIQUE] INDEX IF NOT EXISTS name ON table(col, ...)) only when
    the index is absent; afterwards it must be present and match. Returns True if created."""
    match = _INDEX_STATEMENT.match(statement)
    if match is None:
        raise SchemaUpgradeError("unsupported_index_statement")
    unique, name, table = bool(match.group(1)), match.group(2), match.group(3)
    columns = [column.strip() for column in match.group(4).split(",")]
    if _pg_index_state(connection, name, table, columns, unique) == "ok":
        return False
    connection.execute(statement)
    if _pg_index_state(connection, name, table, columns, unique) != "ok":
        raise SchemaUpgradeError(f"index_still_missing: {name}")
    return True


def _add_columns(connection: Any, table: str, definitions: list[str], is_postgres: bool) -> None:
    if is_postgres:
        ensure_pg_columns(connection, table, definitions)
        return
    existing = _sqlite_column_names(connection, table)
    for definition in definitions:
        name = definition.split(maxsplit=1)[0]
        if name not in existing:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {definition}")
