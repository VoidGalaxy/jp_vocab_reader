"""P-RB tool contract 15-4: the check scope of the completed release. Read only, counts only.

- A (`account`): the target account's OWN rows only -- every input is in the verification
  digest D or changes only under the target's account lock. Rows of other accounts are not
  read to reach a pass.
- N (`inflow`): rows NOT of the target (other owners, an unreadable or missing owner) that
  point into the target's identity spaces, compared space by space (personal card ids,
  personal / subscribed log ids, the target's runs, snapshots and blocks). A subscribed card
  is the (account, lexeme) pair: another account studying the same lexeme is not an inflow.
  A reference that cannot be shown to lie OUTSIDE the target's spaces is `unknown`, never 0.
- S (`sequence`): the unchanged E-4 I3 observation over EVERY account's personal card
  references, now a gate.
- G (`diagnostics`): the unchanged E-4 I1..I5, shown as they are; not a gate.

N and S are observations: other accounts' writes are not stopped by the target's lock, and a
direct SQL change or a sequence reset after the read is not seen."""

from __future__ import annotations

import json
from typing import Any

from app.srs import identity, invariant_audit, migration

KINDS = ("personal", "lexeme")
_id = invariant_audit._id
_result = invariant_audit._result


def _rows(connection: Any, query: str, params: tuple = ()) -> list[dict]:
    return [dict(row) for row in connection.execute(query, params).fetchall()]


def _body(raw: Any) -> Any:
    try:
        return json.loads(raw)
    except (TypeError, ValueError, RecursionError):
        return None


def _runs(connection: Any) -> list[tuple[dict, Any]]:
    return [(row, _body(row["scope_json"])) for row in _rows(connection, "SELECT * FROM srs_migration_runs ORDER BY id")]


def _owner(scope: Any) -> Any:
    return scope.get("user_id") if isinstance(scope, dict) else None


def _run_personal_refs(row: dict, scope: Any) -> list[Any] | None:
    """Every personal ref of a run's scope cards and summary entries; None when unreadable."""
    refs = []
    cards = scope.get("cards", []) if isinstance(scope, dict) else None
    if not isinstance(cards, list):
        return None
    for card in cards:
        if not isinstance(card, dict) or card.get("kind") not in KINDS:
            return None
        if card["kind"] == "personal":
            refs.append(card.get("ref_id"))
    if row["summary_json"] is not None:
        summary = _body(row["summary_json"])
        if isinstance(summary, dict):
            summary = summary.get("results")
        if not isinstance(summary, list):
            return None
        for entry in summary:
            if not isinstance(entry, dict) or entry.get("kind") not in KINDS:
                return None
            if entry["kind"] == "personal":
                refs.append(entry.get("ref_id"))
    return refs


class _Target:
    """The target's own rows, read once on the caller's connection."""

    def __init__(self, connection: Any, user_id: int):
        self.c, self.u = connection, user_id
        one = (user_id,)
        self.cards = {"personal": _rows(connection, "SELECT * FROM vocab_items WHERE user_id = ?", one),
                      "lexeme": _rows(connection, "SELECT * FROM user_word_progress WHERE user_id = ?", one)}
        self.logs = {"personal": _rows(connection, "SELECT * FROM review_logs WHERE user_id = ?", one),
                     "lexeme": _rows(connection, "SELECT * FROM lexeme_review_logs WHERE user_id = ?", one)}
        self.receipts = _rows(connection, "SELECT * FROM srs_review_receipts WHERE user_id = ?", one)
        self.snaps = _rows(connection, "SELECT * FROM srs_migration_snapshots WHERE user_id = ?", one)
        self.deletions = _rows(connection, "SELECT * FROM srs_card_deletions WHERE user_id = ?", one)
        self.flags = _rows(connection, "SELECT * FROM srs_card_identity_flags WHERE user_id = ?", one)
        self.restarts = _rows(connection, "SELECT * FROM srs_evidence_restarts WHERE user_id = ?", one)
        self.blocks = _rows(connection, "SELECT * FROM account_write_blocks WHERE user_id = ? OR active_user_id = ?",
                            (user_id, user_id))
        self.records = _rows(connection, "SELECT * FROM account_recovery_runs WHERE user_id = ? OR active_user_id = ?",
                             (user_id, user_id))
        runs = _runs(connection)
        self.runs = {row["id"]: (row, scope) for row, scope in runs if _owner(scope) == user_id}
        self.unreadable_runs = {row["id"] for row, scope in runs if not isinstance(scope, dict)}
        self.log_index = {kind: {r["id"]: r for r in rows} for kind, rows in self.logs.items()}

    # ---- the target's identity spaces (N compares against these) -------------------------
    def spaces(self) -> dict[str, set]:
        cards = {r["id"] for r in self.cards["personal"] if _id(r["id"])}
        cards |= {r["vocab_item_id"] for r in self.logs["personal"] if _id(r["vocab_item_id"])}
        for rows in (self.receipts, self.snaps, self.deletions, self.flags, self.restarts):
            cards |= {r["card_ref"] for r in rows if r["card_kind"] == "personal" and _id(r["card_ref"])}
        for row, scope in self.runs.values():
            cards |= {ref for ref in (_run_personal_refs(row, scope) or []) if _id(ref)}
        return {"card": cards,
                "personal": {r["id"] for r in self.logs["personal"]},
                "lexeme": {r["id"] for r in self.logs["lexeme"]},
                "run": set(self.runs), "snapshot": {r["id"] for r in self.snaps},
                "block": {r["id"] for r in self.blocks if r["user_id"] == self.u}}


# ---- A: the target's own rows -----------------------------------------------------------------
def account(connection: Any, user_id: int) -> dict:
    """I1a, I2a, I4a, I5a (contract 15-4 A)."""
    t = _Target(connection, user_id)
    i1a, i2a = _ownership(t)
    return {"I1a": i1a, "I2a": i2a, "I4a": _identities(t), "I5a": _log_references(t)}


def _ownership(t: _Target) -> tuple[dict, dict]:
    cards = {r["id"] for r in t.cards["personal"]}
    ledger = {r["card_ref"] for r in t.deletions if r["card_kind"] == "personal"}
    orphan = wrong = unknown = 0
    for log in t.logs["personal"]:
        ref = log["vocab_item_id"]
        if not _id(ref):
            unknown += 1
        elif ref in cards or ref in ledger:
            continue                       # the target's card, or its ledger-proven deletion
        elif t.c.execute("SELECT 1 FROM vocab_items WHERE id = ?", (ref,)).fetchone() is not None:
            wrong += 1                     # labels the failure only: outside the target it fails either way
        else:
            orphan += 1
    subscribed = {r["lexeme_id"] for r in t.cards["lexeme"]}
    missing_progress = sum(r["lexeme_id"] not in subscribed for r in t.logs["lexeme"])
    bad = 0
    blocks = {b["id"]: b for b in t.blocks}
    for block in t.blocks:
        bad += (block["user_id"] != t.u
                or (block["active_user_id"] is not None and block["active_user_id"] != block["user_id"])
                or (block["status"] == "active") != (block["active_user_id"] is not None))
    for run in t.records:
        block = blocks.get(run["block_id"])
        bad += (run["user_id"] != t.u
                or (run["active_user_id"] is not None and run["active_user_id"] != run["user_id"])
                or (run["state"] != "closed") != (run["active_user_id"] is not None)
                or block is None or block["user_id"] != run["user_id"] or block["recovery_key"] != run["recovery_key"])
    for snap in t.snaps:                   # a target snapshot belongs to a target run
        if snap["run_id"] not in t.runs:
            if snap["run_id"] in t.unreadable_runs:
                unknown += 1
            else:
                orphan += 1
    # Review fix: a target subscribed log without its (account, lexeme) progress row is a
    # violation of the gate, not only a count (no app path deletes progress rows).
    return (_result(orphan + bad, unknown),
            _result(wrong + missing_progress, unknown, subscribed_logs_without_progress=missing_progress))


def _identities(t: _Target) -> dict:
    try:
        scan = identity.scan_identity(t.c, user_id=t.u)
    except (identity.IdentityError, ValueError, TypeError, KeyError, RecursionError):
        return _result(unknown=1)
    marked = {r["card_ref"] for r in t.flags if r["card_kind"] == "personal"}
    missing = sum(f.user_id != t.u or f.card_ref not in marked for f in scan.findings)
    return _result(missing, len(scan.undetermined), findings=len(scan.findings), cards_checked=scan.cards_checked)


def _log_references(t: _Target) -> dict:
    """Every log reference of a target row names a target log of the same kind and card."""
    wrong = unknown = checked = 0

    def log_ref(kind: Any, ref: Any, value: Any, *, zero: bool = False) -> None:
        nonlocal wrong, unknown, checked
        if zero and type(value) is int and value == 0:
            return
        checked += 1
        if kind not in KINDS or not _id(ref) or not _id(value):
            unknown += 1
            return
        row = t.log_index[kind].get(value)
        wrong += row is None or row["vocab_item_id" if kind == "personal" else "lexeme_id"] != ref

    snapshots = {r["id"]: r for r in t.snaps}

    def snapshot_ref(row: dict, value: Any) -> None:
        """restart.rollback_record_id (apply records, formats 1-3) is a SNAPSHOT id: a target
        rollback record of the same card. 0 is the allowed empty value."""
        nonlocal wrong, unknown, checked
        if type(value) is int and value == 0:
            return
        checked += 1
        if not _id(value):
            unknown += 1
            return
        source = snapshots.get(value)
        run = t.runs.get(source["run_id"]) if source is not None else None
        wrong += (source is None or run is None or run[0]["mode"] != "rollback"
                  or source["card_kind"] != row["card_kind"] or source["card_ref"] != row["card_ref"])

    for kind, rows in t.cards.items():
        for row in rows:
            if row["evidence_from_log_id"] is not None:
                log_ref(kind, row["id" if kind == "personal" else "lexeme_id"], row["evidence_from_log_id"])
    for row in t.receipts:
        if row["review_log_id"] is not None:
            log_ref(row["card_kind"], row["card_ref"], row["review_log_id"])
    for row in t.snaps:
        body = _body(row["legacy_json"])
        run = t.runs.get(row["run_id"])
        if not isinstance(body, dict) or not isinstance(body.get("card"), dict) or run is None:
            unknown += 1
            continue
        if run[0]["mode"] not in ("apply", "rollback") or migration._record_shape(
                run[0]["mode"], row["card_kind"], row["card_ref"], body,
                migration._card_columns(t.c, row["card_kind"])) is None:
            unknown += 1
        try:
            if "last_log_id" in body:
                log_ref(row["card_kind"], row["card_ref"], body["last_log_id"], zero=True)
            if isinstance(body.get("baseline"), dict) and "last_log_id" in body["baseline"]:
                log_ref(row["card_kind"], row["card_ref"], body["baseline"]["last_log_id"], zero=True)
            elif "last_log_id" not in body:
                unknown += 1
            if "restart" in body:
                log_ref(row["card_kind"], row["card_ref"], body["restart"]["previous_boundary"])
                snapshot_ref(row, body["restart"]["rollback_record_id"])
            if body["card"].get("evidence_from_log_id") is not None:
                log_ref(row["card_kind"], row["card_ref"], body["card"]["evidence_from_log_id"])
        except (TypeError, KeyError):
            unknown += 1
    for row in t.restarts:
        for field in ("previous_boundary", "new_boundary"):
            log_ref(row["card_kind"], row["card_ref"], row[field])
        checked += 1
        source = snapshots.get(row["source_snapshot_id"])
        wrong += source is None or source["card_kind"] != row["card_kind"] or source["card_ref"] != row["card_ref"]
    return _result(wrong, unknown, references_checked=checked)


# ---- N: references INTO the target from rows that are not the target's ------------------------
def inflow(connection: Any, user_id: int) -> dict:
    space = _Target(connection, user_id).spaces()
    violations = unknown = checked = 0

    def into(owner: Any, name: Any, value: Any, *, optional: bool = False, zero: bool = False) -> None:
        """`name`: the target space this value would be in; None when the kind is unreadable."""
        nonlocal violations, unknown, checked
        if (optional and value is None) or (zero and type(value) is int and value == 0):
            return
        checked += 1
        if name is None or not _id(value):
            unknown += 1                   # cannot be shown to lie outside the target's spaces
        elif value in space[name]:
            if _id(owner) and owner != user_id:
                violations += 1
            else:
                unknown += 1               # owner missing / unreadable: relation not excluded

    def log_space(kind: Any) -> str | None:
        return kind if kind in KINDS else None

    def card_space(kind: Any) -> str | None:
        return "card" if kind == "personal" else None

    other = "WHERE user_id IS NULL OR user_id <> ?"
    one = (user_id,)
    for row in _rows(connection, f"SELECT id, user_id, evidence_from_log_id FROM vocab_items {other}", one):
        into(row["user_id"], "card", row["id"])
        into(row["user_id"], "personal", row["evidence_from_log_id"], optional=True)
    for row in _rows(connection, f"SELECT user_id, evidence_from_log_id FROM user_word_progress {other}", one):
        into(row["user_id"], "lexeme", row["evidence_from_log_id"], optional=True)
    for row in _rows(connection, f"SELECT user_id, vocab_item_id FROM review_logs {other}", one):
        into(row["user_id"], "card", row["vocab_item_id"])
    for row in _rows(connection, f"SELECT * FROM srs_review_receipts {other}", one):
        if row["card_kind"] != "lexeme":
            into(row["user_id"], card_space(row["card_kind"]), row["card_ref"])
        into(row["user_id"], log_space(row["card_kind"]), row["review_log_id"], optional=True)
    for row in _rows(connection, f"SELECT * FROM srs_migration_snapshots {other}", one):
        owner, kind = row["user_id"], row["card_kind"]
        into(owner, "run", row["run_id"])
        if kind != "lexeme":
            into(owner, card_space(kind), row["card_ref"])
        body = _body(row["legacy_json"])
        card = body.get("card") if isinstance(body, dict) else None
        if not isinstance(card, dict):
            into(owner, None, None)        # unreadable body: its references are unknown
            continue
        if kind != "lexeme":
            into(owner, card_space(kind), card.get("id"))
        try:
            if "last_log_id" in body:
                into(owner, log_space(kind), body["last_log_id"], zero=True)
            if isinstance(body.get("baseline"), dict) and "last_log_id" in body["baseline"]:
                into(owner, log_space(kind), body["baseline"]["last_log_id"], zero=True)
            if "restart" in body:
                into(owner, log_space(kind), body["restart"]["previous_boundary"])
                # a snapshot id, not a log id (review fix); 0 is the allowed empty value
                into(owner, "snapshot", body["restart"]["rollback_record_id"], zero=True)
            into(owner, log_space(kind), card.get("evidence_from_log_id"), optional=True)
        except (TypeError, KeyError, AttributeError):
            into(owner, None, None)
    for table in ("srs_card_deletions", "srs_card_identity_flags"):
        for row in _rows(connection, f"SELECT user_id, card_kind, card_ref FROM {table} {other}", one):
            into(row["user_id"], card_space(row["card_kind"]), row["card_ref"])
    for row in _rows(connection, f"SELECT * FROM srs_evidence_restarts {other}", one):
        if row["card_kind"] != "lexeme":
            into(row["user_id"], card_space(row["card_kind"]), row["card_ref"])
        for field in ("previous_boundary", "new_boundary"):
            into(row["user_id"], log_space(row["card_kind"]), row[field])
        into(row["user_id"], "snapshot", row["source_snapshot_id"])
    for row in _rows(connection, f"SELECT user_id, vocabulary_id FROM meaning_feedback {other}", one):
        into(row["user_id"], "card", row["vocabulary_id"], optional=True)
    for row, scope in _runs(connection):
        owner = _owner(scope)
        if owner == user_id:
            continue
        refs = _run_personal_refs(row, scope)
        if refs is None:
            into(owner, None, None)        # unreadable scope or summary: owner and cards unknown
            continue
        if row["mode"] == "rollback":
            into(owner, "run", scope.get("source_run_id"))
        for ref in refs:
            into(owner, "card", ref)
    for row in _rows(connection, "SELECT user_id, block_id, active_user_id FROM account_recovery_runs "
                                 "WHERE user_id <> ? OR user_id IS NULL", one):
        into(row["user_id"], "block", row["block_id"])
        violations += row["active_user_id"] == user_id
    for row in _rows(connection, "SELECT user_id FROM account_write_blocks WHERE active_user_id = ? AND "
                                 "(user_id <> ? OR user_id IS NULL)", (user_id, user_id)):
        violations += 1
    return _result(violations, unknown, references_checked=checked)


# ---- S and G ----------------------------------------------------------------------------------
def sequence(connection: Any) -> dict:
    """E-4 I3 unchanged, over every account (SQLite / PostgreSQL semantics, ties and the PG
    `is_called` boundary as there). Not a lock: an observation."""
    return invariant_audit._Audit(connection).sequence()


def diagnostics(connection: Any) -> dict:
    """E-4 I1..I5 as they are (status, violations, unknown); needs the read-only snapshot."""
    checks = invariant_audit.audit(connection)["checks"]
    return {name: {"status": checks[name]["status"], "violations": checks[name].get("violations", 0),
                   "unknown": checks[name].get("unknown", 0)} for name in ("I1", "I2", "I3", "I4", "I5")}
