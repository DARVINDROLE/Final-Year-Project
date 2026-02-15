from __future__ import annotations

import hashlib
import json
import os
import secrets
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path


def _safe_json_dumps(obj) -> str:
    """JSON serializer that handles datetime objects."""
    def default(o):
        if isinstance(o, datetime):
            return o.isoformat()
        raise TypeError(f"Object of type {type(o).__name__} is not JSON serializable")
    return json.dumps(obj, default=default)


class Database:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=5)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def initialize(self) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    created_at TEXT,
                    status TEXT,
                    device_id TEXT,
                    last_updated TEXT,
                    risk_score REAL DEFAULT 0
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS transcripts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT,
                    role TEXT,
                    content TEXT,
                    timestamp TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS visitors (
                    session_id TEXT PRIMARY KEY,
                    image_path TEXT,
                    visitor_type TEXT,
                    ai_summary TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS actions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT,
                    action_type TEXT,
                    payload TEXT,
                    status TEXT,
                    timestamp TEXT,
                    short_reason TEXT,
                    agent_name TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS owners (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    salt TEXT NOT NULL,
                    name TEXT DEFAULT '',
                    created_at TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS members (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    owner_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    phone TEXT DEFAULT '',
                    role TEXT DEFAULT 'family',
                    photo_path TEXT DEFAULT '',
                    permitted INTEGER DEFAULT 1,
                    created_at TEXT,
                    FOREIGN KEY (owner_id) REFERENCES owners(id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tokens (
                    token TEXT PRIMARY KEY,
                    owner_id INTEGER NOT NULL,
                    created_at TEXT,
                    FOREIGN KEY (owner_id) REFERENCES owners(id)
                )
                """
            )
            conn.commit()

    def create_session(self, session_id: str, created_at: str, device_id: str, status: str = "queued") -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                """
                INSERT INTO sessions (id, created_at, status, device_id, last_updated, risk_score)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (session_id, created_at, status, device_id, created_at, 0.0),
            )
            conn.commit()

    def update_session(self, session_id: str, status: str, risk_score: float | None = None) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with closing(self._connect()) as conn:
            if risk_score is None:
                conn.execute(
                    """
                    UPDATE sessions
                    SET status = ?, last_updated = ?
                    WHERE id = ?
                    """,
                    (status, now, session_id),
                )
            else:
                conn.execute(
                    """
                    UPDATE sessions
                    SET status = ?, last_updated = ?, risk_score = ?
                    WHERE id = ?
                    """,
                    (status, now, risk_score, session_id),
                )
            conn.commit()

    def get_session(self, session_id: str) -> dict | None:
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
            return dict(row) if row else None

    def add_transcript(self, session_id: str, role: str, content: str, timestamp: str | None = None) -> None:
        ts = timestamp or datetime.now(timezone.utc).isoformat()
        with closing(self._connect()) as conn:
            conn.execute(
                """
                INSERT INTO transcripts (session_id, role, content, timestamp)
                VALUES (?, ?, ?, ?)
                """,
                (session_id, role, content, ts),
            )
            conn.commit()

    def upsert_visitor(self, session_id: str, image_path: str, visitor_type: str = "unknown", ai_summary: str = "") -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                """
                INSERT INTO visitors (session_id, image_path, visitor_type, ai_summary)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(session_id)
                DO UPDATE SET
                    image_path = excluded.image_path,
                    visitor_type = excluded.visitor_type,
                    ai_summary = excluded.ai_summary
                """,
                (session_id, image_path, visitor_type, ai_summary),
            )
            conn.commit()

    def add_action(
        self,
        session_id: str,
        action_type: str,
        payload: dict,
        status: str,
        short_reason: str = "",
        agent_name: str = "orchestrator",
        timestamp: str | None = None,
    ) -> None:
        ts = timestamp or datetime.now(timezone.utc).isoformat()
        with closing(self._connect()) as conn:
            conn.execute(
                """
                INSERT INTO actions (session_id, action_type, payload, status, timestamp, short_reason, agent_name)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (session_id, action_type, _safe_json_dumps(payload), status, ts, short_reason, agent_name),
            )
            conn.commit()

    def get_recent_logs(self, limit: int = 50) -> dict:
        with closing(self._connect()) as conn:
            sessions = [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT id, created_at, status, device_id, last_updated, risk_score
                    FROM sessions
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
            ]
            transcripts = [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT id, session_id, role, content, timestamp
                    FROM transcripts
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
            ]
            actions = [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT id, session_id, action_type, payload, status, timestamp, short_reason, agent_name
                    FROM actions
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
            ]
            visitors = [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT session_id, image_path, visitor_type, ai_summary
                    FROM visitors
                    ORDER BY rowid DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
            ]
            return {
                "sessions": sessions,
                "transcripts": transcripts,
                "actions": actions,
                "visitors": visitors,
            }

    # ── Auth helpers ──────────────────────────────────────────

    @staticmethod
    def _hash_password(password: str, salt: str) -> str:
        return hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000).hex()

    def register_owner(self, username: str, password: str, name: str = "") -> dict | None:
        salt = secrets.token_hex(16)
        pw_hash = self._hash_password(password, salt)
        ts = datetime.now(timezone.utc).isoformat()
        with closing(self._connect()) as conn:
            try:
                conn.execute(
                    "INSERT INTO owners (username, password_hash, salt, name, created_at) VALUES (?, ?, ?, ?, ?)",
                    (username, pw_hash, salt, name, ts),
                )
                conn.commit()
                owner_id = conn.execute("SELECT id FROM owners WHERE username = ?", (username,)).fetchone()
                return {"id": owner_id["id"], "username": username, "name": name}
            except sqlite3.IntegrityError:
                return None

    def verify_owner(self, username: str, password: str) -> dict | None:
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT * FROM owners WHERE username = ?", (username,)).fetchone()
            if not row:
                return None
            if self._hash_password(password, row["salt"]) != row["password_hash"]:
                return None
            return {"id": row["id"], "username": row["username"], "name": row["name"]}

    def create_token(self, owner_id: int) -> str:
        token = secrets.token_urlsafe(32)
        ts = datetime.now(timezone.utc).isoformat()
        with closing(self._connect()) as conn:
            conn.execute("INSERT INTO tokens (token, owner_id, created_at) VALUES (?, ?, ?)", (token, owner_id, ts))
            conn.commit()
        return token

    def verify_token(self, token: str) -> dict | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT o.id, o.username, o.name FROM tokens t JOIN owners o ON t.owner_id = o.id WHERE t.token = ?",
                (token,),
            ).fetchone()
            return dict(row) if row else None

    def delete_token(self, token: str) -> None:
        with closing(self._connect()) as conn:
            conn.execute("DELETE FROM tokens WHERE token = ?", (token,))
            conn.commit()

    # ── Member helpers ────────────────────────────────────────

    def add_member(self, owner_id: int, name: str, phone: str = "", role: str = "family", photo_path: str = "") -> dict:
        ts = datetime.now(timezone.utc).isoformat()
        with closing(self._connect()) as conn:
            cur = conn.execute(
                "INSERT INTO members (owner_id, name, phone, role, photo_path, permitted, created_at) VALUES (?, ?, ?, ?, ?, 1, ?)",
                (owner_id, name, phone, role, photo_path, ts),
            )
            conn.commit()
            return {"id": cur.lastrowid, "name": name, "phone": phone, "role": role, "photo_path": photo_path, "permitted": True}

    def get_members(self, owner_id: int) -> list[dict]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT id, name, phone, role, photo_path, permitted, created_at FROM members WHERE owner_id = ? ORDER BY created_at DESC",
                (owner_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def update_member(self, member_id: int, owner_id: int, **kwargs) -> bool:
        allowed = {"name", "phone", "role", "photo_path", "permitted"}
        updates = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
        if not updates:
            return False
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [member_id, owner_id]
        with closing(self._connect()) as conn:
            cur = conn.execute(
                f"UPDATE members SET {set_clause} WHERE id = ? AND owner_id = ?",
                values,
            )
            conn.commit()
            return cur.rowcount > 0

    def delete_member(self, member_id: int, owner_id: int) -> bool:
        with closing(self._connect()) as conn:
            cur = conn.execute("DELETE FROM members WHERE id = ? AND owner_id = ?", (member_id, owner_id))
            conn.commit()
            return cur.rowcount > 0

    # ── Session detail helper ─────────────────────────────────

    def get_session_detail(self, session_id: str) -> dict | None:
        """Get full session detail with visitor, transcripts, and actions."""
        with closing(self._connect()) as conn:
            session = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
            if not session:
                return None
            visitor = conn.execute("SELECT * FROM visitors WHERE session_id = ?", (session_id,)).fetchone()
            transcripts = conn.execute(
                "SELECT role, content, timestamp FROM transcripts WHERE session_id = ? ORDER BY id",
                (session_id,),
            ).fetchall()
            actions = conn.execute(
                "SELECT action_type, payload, status, short_reason, agent_name, timestamp FROM actions WHERE session_id = ? ORDER BY id",
                (session_id,),
            ).fetchall()
            return {
                "session": dict(session),
                "visitor": dict(visitor) if visitor else None,
                "transcripts": [dict(t) for t in transcripts],
                "actions": [dict(a) for a in actions],
            }
