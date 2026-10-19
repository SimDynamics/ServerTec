"""Authoritative, atomic FREE evaluations over canonical consumption histories.

An attempt ID belongs to an authenticated account, never to its mutable group or
device. Results and receipts are durable. Identical answers under another ID
reuse their result without another debit. No network, code execution or timers
run in the writer transaction. Catalog rules are immutable, bounded pure data.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from uuid import UUID

from account_ledger import AccountLedger, LedgerError, _integer


MAX_PENDING_PER_ACCOUNT = 32
MAX_ANSWER_BYTES = 8192
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_./:-]{0,255}")
_VERSION = re.compile(r"[0-9a-f]{64}")

_SCHEMA = (
    "CREATE TABLE evaluation_meta(key TEXT PRIMARY KEY, value TEXT NOT NULL)",
    """CREATE TABLE evaluation_results(
        account_id TEXT NOT NULL REFERENCES auth_accounts(account_id),
        request_hash TEXT NOT NULL CHECK(length(request_hash)=64),
        exercise_id TEXT NOT NULL,
        exercise_version TEXT NOT NULL CHECK(length(exercise_version)=64),
        route TEXT NOT NULL CHECK(route IN ('programming','math_physics')),
        correct INTEGER NOT NULL CHECK(typeof(correct)='integer' AND correct IN (0,1)),
        evaluated_at_ms INTEGER NOT NULL CHECK(typeof(evaluated_at_ms)='integer' AND evaluated_at_ms>=0),
        PRIMARY KEY(account_id,request_hash))""",
    """CREATE TABLE evaluation_attempts(
        account_id TEXT NOT NULL REFERENCES auth_accounts(account_id),
        attempt_id TEXT NOT NULL CHECK(length(attempt_id)=36),
        request_hash TEXT NOT NULL CHECK(length(request_hash)=64),
        exercise_id TEXT NOT NULL,
        exercise_version TEXT NOT NULL CHECK(length(exercise_version)=64),
        created_at_ms INTEGER NOT NULL CHECK(typeof(created_at_ms)='integer' AND created_at_ms>=0),
        result_hash TEXT,
        confirmed_at_ms INTEGER,
        charged_hearts INTEGER,
        duplicate_answer INTEGER,
        PRIMARY KEY(account_id,attempt_id),
        FOREIGN KEY(account_id,result_hash) REFERENCES evaluation_results(account_id,request_hash),
        CHECK(result_hash IS NULL OR result_hash=request_hash),
        CHECK((result_hash IS NULL AND confirmed_at_ms IS NULL AND charged_hearts IS NULL
               AND duplicate_answer IS NULL) OR
              (result_hash IS NOT NULL AND typeof(confirmed_at_ms)='integer'
               AND confirmed_at_ms>=created_at_ms AND typeof(charged_hearts)='integer'
               AND charged_hearts IN (0,1) AND typeof(duplicate_answer)='integer'
               AND duplicate_answer IN (0,1) AND NOT(charged_hearts=1 AND duplicate_answer=1))))""",
    """CREATE INDEX evaluation_pending ON evaluation_attempts(account_id)
        WHERE result_hash IS NULL""",
    """CREATE TRIGGER evaluation_result_immutable BEFORE UPDATE ON evaluation_results
        BEGIN SELECT RAISE(ABORT,'evaluation_result_is_immutable'); END""",
    """CREATE TRIGGER evaluation_result_retained BEFORE DELETE ON evaluation_results
        BEGIN SELECT RAISE(ABORT,'evaluation_result_is_retained'); END""",
    """CREATE TRIGGER evaluation_attempt_immutable BEFORE UPDATE ON evaluation_attempts
        WHEN OLD.result_hash IS NOT NULL OR NEW.account_id IS NOT OLD.account_id
        OR NEW.attempt_id IS NOT OLD.attempt_id OR NEW.request_hash IS NOT OLD.request_hash
        OR NEW.exercise_id IS NOT OLD.exercise_id OR NEW.exercise_version IS NOT OLD.exercise_version
        OR NEW.created_at_ms IS NOT OLD.created_at_ms
        BEGIN SELECT RAISE(ABORT,'evaluation_attempt_is_immutable'); END""",
    """CREATE TRIGGER evaluation_attempt_retained BEFORE DELETE ON evaluation_attempts
        BEGIN SELECT RAISE(ABORT,'evaluation_attempt_is_retained'); END""",
)


def canonical_answer(answer: object) -> str:
    """Bound JSON work and preserve types/whitespace; never accept NaN or floats.

    Curriculum numeric answers travel as strings (including fractions), not
    binary floating-point. Mapping order is immaterial; sequence order matters.
    Rule-specific validity and completeness are checked separately by the rule.
    """
    remaining = 1024

    def visit(value, depth=0):
        nonlocal remaining
        remaining -= 1
        if remaining < 0 or depth > 12:
            raise LedgerError("invalid_answer", 422)
        if value is None or type(value) is bool:
            return
        if type(value) is int:
            if not -(1 << 63) <= value < (1 << 63):
                raise LedgerError("invalid_answer", 422)
        elif type(value) is str:
            if len(value) > MAX_ANSWER_BYTES:
                raise LedgerError("invalid_answer", 422)
        elif type(value) is list:
            if len(value) > 256:
                raise LedgerError("invalid_answer", 422)
            for item in value:
                visit(item, depth + 1)
        elif type(value) is dict:
            if len(value) > 256:
                raise LedgerError("invalid_answer", 422)
            for key, item in value.items():
                if type(key) is not str or len(key) > 256:
                    raise LedgerError("invalid_answer", 422)
                visit(item, depth + 1)
        else:
            raise LedgerError("invalid_answer", 422)

    visit(answer)
    try:
        value = json.dumps(answer, sort_keys=True, ensure_ascii=False,
                           allow_nan=False, separators=(",", ":"))
        if len(value.encode("utf-8")) > MAX_ANSWER_BYTES:
            raise LedgerError("invalid_answer", 422)
    except (UnicodeError, ValueError, TypeError, RecursionError):
        raise LedgerError("invalid_answer", 422) from None
    return value


def _request(attempt_id, exercise_id, exercise_version, answer):
    if type(attempt_id) is not str or len(attempt_id) != 36:
        raise LedgerError("invalid_attempt_id", 422)
    try:
        normalized = str(UUID(attempt_id))
    except ValueError:
        raise LedgerError("invalid_attempt_id", 422) from None
    if normalized != attempt_id.lower():
        raise LedgerError("invalid_attempt_id", 422)
    if type(exercise_id) is not str or _ID.fullmatch(exercise_id) is None:
        raise LedgerError("invalid_exercise_id", 422)
    if type(exercise_version) is not str or _VERSION.fullmatch(exercise_version) is None:
        raise LedgerError("invalid_exercise_version", 422)
    # Encode identifiers separately from the exact canonical response. The
    # namespace prevents accidental reuse as another application's hash.
    payload = ("servertec-evaluation-v1\0" + exercise_id + "\0" + exercise_version
               + "\0" + canonical_answer(answer)).encode("utf-8")
    return normalized, hashlib.sha256(payload).hexdigest()


class EvaluationService:
    def __init__(self, groups, catalog):
        self.groups, self.catalog = groups, catalog
        self._initialize()

    def _initialize(self):
        # Additive migration. The independent auth marker prevents recreating
        # lost result tables and treating previously charged attempts as new.
        with self.groups.transaction() as con:
            existing = {row["name"]: row["sql"] for row in con.execute(
                "SELECT name,sql FROM sqlite_master WHERE type IN ('table','index','trigger')")}
            expected = {sql.split()[2].split("(")[0]: sql for sql in _SCHEMA}
            guard = con.execute("SELECT value FROM auth_meta WHERE key='evaluations'").fetchone()
            if "evaluation_meta" not in existing:
                if guard is not None or set(expected).intersection(existing):
                    raise RuntimeError("Evaluation schema missing; do not reset receipts")
                for sql in _SCHEMA:
                    con.execute(sql)
                con.execute("INSERT INTO evaluation_meta VALUES('version','1')")
                con.execute("INSERT INTO auth_meta VALUES('evaluations','1')")
            else:
                version = con.execute("SELECT value FROM evaluation_meta WHERE key='version'").fetchone()
                if guard is None or guard[0] != "1" or version is None or version[0] != "1":
                    raise RuntimeError("Unsupported evaluation schema; do not reset receipts")
                for name, sql in expected.items():
                    if " ".join((existing.get(name) or "").split()) != " ".join(sql.split()):
                        raise RuntimeError("Evaluation schema damaged; do not reset receipts")

    @staticmethod
    def _result(con, account_id, request_hash):
        return con.execute("SELECT * FROM evaluation_results WHERE account_id=? AND request_hash=?",
                           (account_id, request_hash)).fetchone()

    @staticmethod
    def _check_result(row, exercise_id, exercise_version):
        if row is None or row["exercise_id"] != exercise_id or row["exercise_version"] != exercise_version:
            raise LedgerError("evaluation_state_corrupt", 503)
        if type(row["correct"]) is not int or row["correct"] not in (0, 1) or not _integer(row["evaluated_at_ms"]):
            raise LedgerError("evaluation_state_corrupt", 503)
        if row["route"] not in ("programming", "math_physics"):
            raise LedgerError("evaluation_state_corrupt", 503)

    @staticmethod
    def _insert_attempt(con, account_id, attempt_id, request_hash, exercise_id, version, now):
        con.execute("""INSERT INTO evaluation_attempts
            (account_id,attempt_id,request_hash,exercise_id,exercise_version,created_at_ms)
            VALUES(?,?,?,?,?,?)""", (account_id, attempt_id, request_hash, exercise_id, version, now))

    @staticmethod
    def _confirm(con, account_id, attempt_id, request_hash, now, charged, duplicate):
        changed = con.execute("""UPDATE evaluation_attempts SET result_hash=?,confirmed_at_ms=?,
            charged_hearts=?,duplicate_answer=? WHERE account_id=? AND attempt_id=? AND result_hash IS NULL""",
            (request_hash, now, charged, int(duplicate), account_id, attempt_id))
        if changed.rowcount != 1:
            raise LedgerError("evaluation_state_corrupt", 503)

    @staticmethod
    def _reply(con, account_id, attempt_id, result, hearts, *, replayed):
        attempt = con.execute("SELECT * FROM evaluation_attempts WHERE account_id=? AND attempt_id=?",
                              (account_id, attempt_id)).fetchone()
        if (attempt is None or attempt["result_hash"] != result["request_hash"]
                or attempt["charged_hearts"] not in (0, 1) or attempt["duplicate_answer"] not in (0, 1)
                or not _integer(attempt["confirmed_at_ms"])
                or (result["correct"] and attempt["charged_hearts"])):
            raise LedgerError("evaluation_state_corrupt", 503)
        return {
            "status": "evaluated",
            "replayed": replayed,
            "receipt": {
                "attempt_id": attempt_id,
                "exercise_id": attempt["exercise_id"],
                "exercise_version": attempt["exercise_version"],
                "correct": bool(result["correct"]),
                "charged_hearts": attempt["charged_hearts"],
                "duplicate_answer": bool(attempt["duplicate_answer"]),
                "evaluated_at_ms": result["evaluated_at_ms"],
                "confirmed_at_ms": attempt["confirmed_at_ms"],
            },
            "hearts": hearts,
        }

    def evaluate(self, token, android_id, attempt_id, exercise_id, exercise_version, answer):
        attempt_id, request_hash = _request(attempt_id, exercise_id, exercise_version, answer)
        with self.groups.transaction() as con:
            # Read time and credentials AFTER obtaining the writer lock.
            now = self.groups._now()
            account_id, root = self.groups.authorize_in_transaction(con, token, android_id, now=now)
            reply = self._evaluate(con, account_id, root, now, attempt_id, request_hash,
                                   exercise_id, exercise_version, answer)
        # A result never escapes until the context manager has committed.
        return reply

    def _evaluate(self, con, account_id, root, now, attempt_id, request_hash,
                  exercise_id, exercise_version, answer):
        attempt = con.execute("SELECT * FROM evaluation_attempts WHERE account_id=? AND attempt_id=?",
                              (account_id, attempt_id)).fetchone()
        if attempt is not None:
            if (attempt["request_hash"] != request_hash or attempt["exercise_id"] != exercise_id
                    or attempt["exercise_version"] != exercise_version):
                raise LedgerError("attempt_conflict", 409)
            if not _integer(attempt["created_at_ms"]):
                raise LedgerError("evaluation_state_corrupt", 503)
            if attempt["result_hash"] is not None:
                result = self._result(con, account_id, attempt["result_hash"])
                self._check_result(result, exercise_id, exercise_version)
                hearts = self.groups._update(con, account_id, root, result["route"], now, debit=False)
                return self._reply(con, account_id, attempt_id, result, hearts, replayed=True)

        # Semantic repeats (A -> B -> A) use the same stored result but own a
        # new receipt. This is not a new evaluation and remains possible at 0.
        # Neither form of replay needs the rule to remain in the active catalog.
        result = self._result(con, account_id, request_hash)
        if result is not None:
            self._check_result(result, exercise_id, exercise_version)
            hearts = self.groups._update(con, account_id, root, result["route"], now, debit=False)
            if attempt is None:
                self._insert_attempt(con, account_id, attempt_id, request_hash,
                                     exercise_id, exercise_version, now)
            confirmed = max(now, result["evaluated_at_ms"],
                            attempt["created_at_ms"] if attempt is not None else now)
            self._confirm(con, account_id, attempt_id, request_hash, confirmed, 0, True)
            return self._reply(con, account_id, attempt_id, result, hearts, replayed=False)

        rule = self.catalog.resolve(exercise_id, exercise_version)
        route = AccountLedger._route(rule.route)
        if rule.version != exercise_version:
            raise LedgerError("invalid_evaluator_rule", 503)
        rule.validate_answer(answer)
        hearts = self.groups._update(con, account_id, root, route, now, debit=False)
        if attempt is None:
            if hearts["available"] == 0:
                pending = con.execute("SELECT COUNT(*) FROM evaluation_attempts WHERE account_id=? AND result_hash IS NULL",
                                      (account_id,)).fetchone()[0]
                if pending >= MAX_PENDING_PER_ACCOUNT:
                    raise LedgerError("pending_attempt_limit", 429)
            self._insert_attempt(con, account_id, attempt_id, request_hash,
                                 exercise_id, exercise_version, now)
        if hearts["available"] == 0:
            # Bind a valid pending request to its ID without evaluating it.
            return {"status": "pending", "error": "hearts_empty", "attempt_id": attempt_id, "hearts": hearts}

        correct = rule.evaluate(answer)
        if type(correct) is not bool:
            raise LedgerError("invalid_evaluator_result", 503)
        charged = 0
        if not correct:
            hearts = self.groups._update(con, account_id, root, route, now, debit=True)
            if hearts["status"] != "charged":
                raise LedgerError("evaluation_state_corrupt", 503)
            charged = 1
        evaluated = hearts["server_time_ms"]
        con.execute("""INSERT INTO evaluation_results
            (account_id,request_hash,exercise_id,exercise_version,route,correct,evaluated_at_ms)
            VALUES(?,?,?,?,?,?,?)""", (account_id, request_hash, exercise_id, exercise_version,
                                      route, int(correct), evaluated))
        confirmed = max(evaluated, attempt["created_at_ms"] if attempt is not None else now)
        self._confirm(con, account_id, attempt_id, request_hash, confirmed, charged, False)
        result = self._result(con, account_id, request_hash)
        self._check_result(result, exercise_id, exercise_version)
        return self._reply(con, account_id, attempt_id, result, hearts, replayed=False)
