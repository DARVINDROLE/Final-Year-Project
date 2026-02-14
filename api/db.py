from __future__ import annotations

import json
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
            return {
                "sessions": sessions,
                "transcripts": transcripts,
                "actions": actions,
            }
