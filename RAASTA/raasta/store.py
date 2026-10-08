"""SQLite-backed persistence. Stdlib only, one file, survives power cuts.

Design rule: **the event log is the source of truth.** Everything else (mastery
estimates, streaks, playbook scores) is derived and therefore rebuildable from
scratch. If the derived state is ever wrong, we replay rather than patch.
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from contextlib import contextmanager
from typing import Any, Dict, Iterable, Iterator, List, Optional

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS students (
    id            TEXT PRIMARY KEY,
    created_at    REAL NOT NULL,
    profile_json  TEXT NOT NULL DEFAULT '{}'
);

-- append-only. never UPDATE, never DELETE (except on the student's own request).
CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id  TEXT NOT NULL,
    ts          REAL NOT NULL,
    kind        TEXT NOT NULL,
    payload     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_student ON events(student_id, ts);

CREATE TABLE IF NOT EXISTS skill_state (
    student_id  TEXT NOT NULL,
    skill_id    TEXT NOT NULL,
    state_json  TEXT NOT NULL,
    updated_at  REAL NOT NULL,
    PRIMARY KEY (student_id, skill_id)
);

-- versioned playbook: the system's accumulated teaching knowledge
CREATE TABLE IF NOT EXISTS playbook (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    scope       TEXT NOT NULL,          -- 'global' | 'student:<id>' | 'skill:<id>'
    key         TEXT NOT NULL,
    value       TEXT NOT NULL,
    evidence    TEXT NOT NULL DEFAULT '',
    score       REAL NOT NULL DEFAULT 0.0,
    status      TEXT NOT NULL DEFAULT 'active',   -- active | deprecated
    version     INTEGER NOT NULL DEFAULT 1,
    created_at  REAL NOT NULL,
    updated_at  REAL NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_playbook_unique
    ON playbook(scope, key, version);
CREATE INDEX IF NOT EXISTS idx_playbook_lookup ON playbook(scope, key, status);

CREATE TABLE IF NOT EXISTS reflections (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id  TEXT NOT NULL,
    ts          REAL NOT NULL,
    kind        TEXT NOT NULL,
    text        TEXT NOT NULL,
    metrics     TEXT NOT NULL DEFAULT '{}'
);

-- free-tier quota ledger: without this you hit 429 and the student sees nothing
CREATE TABLE IF NOT EXISTS llm_usage (
    provider    TEXT NOT NULL,
    day         TEXT NOT NULL,
    count       INTEGER NOT NULL DEFAULT 0,
    errors      INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (provider, day)
);

CREATE TABLE IF NOT EXISTS llm_cache (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    created_at  REAL NOT NULL,
    hits        INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS research_notes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          REAL NOT NULL,
    topic       TEXT NOT NULL,
    source      TEXT NOT NULL,
    url_hash    TEXT NOT NULL UNIQUE,
    content     TEXT NOT NULL,
    distilled   TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_research_topic ON research_notes(topic);

CREATE TABLE IF NOT EXISTS eval_runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          REAL NOT NULL,
    suite       TEXT NOT NULL,
    playbook_v  INTEGER NOT NULL,
    metrics     TEXT NOT NULL
);
"""


def _day_key(ts: Optional[float] = None) -> str:
    return time.strftime("%Y-%m-%d", time.gmtime(ts or time.time()))


class Store:
    """Thin, honest wrapper around sqlite3. No ORM magic."""

    def __init__(self, path: str = "raasta.db"):
        self.path = path
        parent = os.path.dirname(os.path.abspath(path))
        if parent:
            os.makedirs(parent, exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init()

    # -- lifecycle ---------------------------------------------------------
    def _init(self) -> None:
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        try:
            self.conn.commit()
        finally:
            self.conn.close()

    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        try:
            yield self.conn
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    # -- students ----------------------------------------------------------
    def upsert_student(self, student_id: str, profile: Dict[str, Any]) -> None:
        now = time.time()
        self.conn.execute(
            "INSERT INTO students(id, created_at, profile_json) VALUES(?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET profile_json=excluded.profile_json",
            (student_id, now, json.dumps(profile, ensure_ascii=False)),
        )
        self.conn.commit()

    def get_student(self, student_id: str) -> Optional[Dict[str, Any]]:
        row = self.conn.execute(
            "SELECT * FROM students WHERE id=?", (student_id,)
        ).fetchone()
        if row is None:
            return None
        out = dict(row)
        out["profile"] = json.loads(row["profile_json"])
        return out

    def list_students(self) -> List[str]:
        return [r["id"] for r in self.conn.execute("SELECT id FROM students")]

    # -- events (append-only) ----------------------------------------------
    def log_event(self, student_id: str, kind: str, payload: Dict[str, Any],
                  ts: Optional[float] = None) -> int:
        cur = self.conn.execute(
            "INSERT INTO events(student_id, ts, kind, payload) VALUES(?,?,?,?)",
            (student_id, ts or time.time(), kind,
             json.dumps(payload, ensure_ascii=False, default=str)),
        )
        self.conn.commit()
        return int(cur.lastrowid or 0)

    def events(self, student_id: str, kind: Optional[str] = None,
               since: Optional[float] = None,
               limit: int = 1000) -> List[Dict[str, Any]]:
        q = "SELECT * FROM events WHERE student_id=?"
        args: List[Any] = [student_id]
        if kind:
            q += " AND kind=?"
            args.append(kind)
        if since is not None:
            q += " AND ts>=?"
            args.append(since)
        q += " ORDER BY ts DESC LIMIT ?"
        args.append(limit)
        out = []
        for r in self.conn.execute(q, args):
            d = dict(r)
            d["payload"] = json.loads(r["payload"])
            out.append(d)
        return out

    def count_events(self, student_id: str, kind: Optional[str] = None) -> int:
        q = "SELECT COUNT(*) c FROM events WHERE student_id=?"
        args: List[Any] = [student_id]
        if kind:
            q += " AND kind=?"
            args.append(kind)
        return int(self.conn.execute(q, args).fetchone()["c"])

    # -- skill state -------------------------------------------------------
    def save_skill(self, student_id: str, skill_id: str, state: Dict[str, Any]) -> None:
        self.conn.execute(
            "INSERT INTO skill_state(student_id, skill_id, state_json, updated_at) "
            "VALUES(?,?,?,?) ON CONFLICT(student_id, skill_id) DO UPDATE SET "
            "state_json=excluded.state_json, updated_at=excluded.updated_at",
            (student_id, skill_id, json.dumps(state, default=str), time.time()),
        )
        self.conn.commit()

    def load_skills(self, student_id: str) -> Dict[str, Dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT skill_id, state_json FROM skill_state WHERE student_id=?",
            (student_id,),
        )
        return {r["skill_id"]: json.loads(r["state_json"]) for r in rows}

    # -- playbook (versioned) ----------------------------------------------
    def playbook_put(self, scope: str, key: str, value: str, evidence: str = "",
                     score: float = 0.0, status: str = "active") -> int:
        """Write a NEW version. We never overwrite; history is how we audit ourselves."""
        row = self.conn.execute(
            "SELECT MAX(version) v FROM playbook WHERE scope=? AND key=?", (scope, key)
        ).fetchone()
        version = int(row["v"] or 0) + 1
        now = time.time()
        self.conn.execute(
            "INSERT INTO playbook(scope,key,value,evidence,score,status,version,"
            "created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (scope, key, value, evidence, score, status, version, now, now),
        )
        self.conn.commit()
        return version

    def playbook_get(self, scope: str, key: str,
                     status: str = "active") -> Optional[Dict[str, Any]]:
        row = self.conn.execute(
            "SELECT * FROM playbook WHERE scope=? AND key=? AND status=? "
            "ORDER BY version DESC LIMIT 1", (scope, key, status)
        ).fetchone()
        return dict(row) if row else None

    def playbook_has_key(self, scope: str, key: str) -> bool:
        """Has this key EVER existed? Used so seeding cannot resurrect a rule
        that the system deliberately deprecated."""
        row = self.conn.execute(
            "SELECT 1 FROM playbook WHERE scope=? AND key=? LIMIT 1", (scope, key)
        ).fetchone()
        return row is not None

    def playbook_scope(self, scope: str, status: str = "active") -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM playbook WHERE scope=? AND status=? ORDER BY key, version DESC",
            (scope, status),
        )
        seen, out = set(), []
        for r in rows:
            if r["key"] in seen:
                continue
            seen.add(r["key"])
            out.append(dict(r))
        return out

    def playbook_version(self, scope: str) -> int:
        row = self.conn.execute(
            "SELECT COALESCE(SUM(version),0) v FROM playbook WHERE scope=?", (scope,)
        ).fetchone()
        return int(row["v"] or 0)

    def playbook_deprecate(self, scope: str, key: str, reason: str = "") -> bool:
        cur = self.conn.execute(
            "UPDATE playbook SET status='deprecated', evidence=?, updated_at=? "
            "WHERE scope=? AND key=? AND status='active'",
            (f"deprecated: {reason}", time.time(), scope, key),
        )
        self.conn.commit()
        return cur.rowcount > 0

    # -- reflections -------------------------------------------------------
    def add_reflection(self, student_id: str, kind: str, text: str,
                       metrics: Optional[Dict[str, Any]] = None) -> None:
        self.conn.execute(
            "INSERT INTO reflections(student_id, ts, kind, text, metrics) VALUES(?,?,?,?,?)",
            (student_id, time.time(), kind, text,
             json.dumps(metrics or {}, default=str)),
        )
        self.conn.commit()

    def reflections(self, student_id: Optional[str] = None,
                    limit: int = 100) -> List[Dict[str, Any]]:
        if student_id:
            rows = self.conn.execute(
                "SELECT * FROM reflections WHERE student_id=? ORDER BY ts DESC LIMIT ?",
                (student_id, limit))
        else:
            rows = self.conn.execute(
                "SELECT * FROM reflections ORDER BY ts DESC LIMIT ?", (limit,))
        out = []
        for r in rows:
            d = dict(r)
            d["metrics"] = json.loads(r["metrics"] or "{}")
            out.append(d)
        return out

    # -- quota ledger ------------------------------------------------------
    def usage_today(self, provider: str, day: Optional[str] = None) -> int:
        row = self.conn.execute(
            "SELECT count FROM llm_usage WHERE provider=? AND day=?",
            (provider, day or _day_key()),
        ).fetchone()
        return int(row["count"]) if row else 0

    def bump_usage(self, provider: str, ok: bool = True) -> None:
        day = _day_key()
        self.conn.execute(
            "INSERT INTO llm_usage(provider, day, count, errors) VALUES(?,?,?,?) "
            "ON CONFLICT(provider, day) DO UPDATE SET count=count+1, "
            "errors=errors+excluded.errors",
            (provider, day, 1, 0 if ok else 1),
        )
        self.conn.commit()

    def usage_report(self, day: Optional[str] = None) -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM llm_usage WHERE day=? ORDER BY count DESC",
            (day or _day_key(),))
        return [dict(r) for r in rows]

    # -- cache -------------------------------------------------------------
    def cache_get(self, key: str) -> Optional[str]:
        row = self.conn.execute("SELECT value FROM llm_cache WHERE key=?", (key,)).fetchone()
        if row is None:
            return None
        self.conn.execute("UPDATE llm_cache SET hits=hits+1 WHERE key=?", (key,))
        return str(row["value"])

    def cache_put(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT INTO llm_cache(key,value,created_at,hits) VALUES(?,?,?,0) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, created_at=excluded.created_at",
            (key, value, time.time()))
        self.conn.commit()

    def cache_clear(self) -> int:
        cur = self.conn.execute("DELETE FROM llm_cache")
        self.conn.commit()
        return int(cur.rowcount or 0)

    # -- research notes ----------------------------------------------------
    def add_research(self, topic: str, source: str, url_hash: str,
                     content: str, distilled: str = "") -> bool:
        try:
            self.conn.execute(
                "INSERT INTO research_notes(ts,topic,source,url_hash,content,distilled)"
                " VALUES(?,?,?,?,?,?)",
                (time.time(), topic, source, url_hash, content, distilled))
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False  # already seen

    def research(self, topic: Optional[str] = None,
                 limit: int = 50) -> List[Dict[str, Any]]:
        q = "SELECT * FROM research_notes"
        args: List[Any] = []
        if topic:
            q += " WHERE topic=?"
            args.append(topic)
        q += " ORDER BY ts DESC LIMIT ?"
        args.append(limit)
        return [dict(r) for r in self.conn.execute(q, args)]

    # -- evals -------------------------------------------------------------
    def record_eval(self, suite: str, playbook_v: int, metrics: Dict[str, Any]) -> None:
        self.conn.execute(
            "INSERT INTO eval_runs(ts,suite,playbook_v,metrics) VALUES(?,?,?,?)",
            (time.time(), suite, playbook_v, json.dumps(metrics, default=str)))
        self.conn.commit()

    def eval_history(self, suite: Optional[str] = None,
                     limit: int = 50) -> List[Dict[str, Any]]:
        q = "SELECT * FROM eval_runs"
        args: List[Any] = []
        if suite:
            q += " WHERE suite=?"
            args.append(suite)
        q += " ORDER BY ts DESC LIMIT ?"
        args.append(limit)
        out = []
        for r in self.conn.execute(q, args):
            d = dict(r)
            d["metrics"] = json.loads(r["metrics"])
            out.append(d)
        return out

    # -- destructive (student's own right to be forgotten) ------------------
    def forget_student(self, student_id: str) -> None:
        with self.tx() as c:
            for tbl, col in (("events", "student_id"), ("skill_state", "student_id"),
                             ("reflections", "student_id"), ("students", "id"),
                             ("playbook", "scope")):
                if tbl == "playbook":
                    c.execute("DELETE FROM playbook WHERE scope=?", (f"student:{student_id}",))
                else:
                    c.execute(f"DELETE FROM {tbl} WHERE {col}=?", (student_id,))
