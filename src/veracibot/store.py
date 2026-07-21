"""Persistência em SQLite: casos julgados e estado do poller."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS cases (
    conversation_id TEXT PRIMARY KEY,
    mention_tweet_id TEXT NOT NULL,
    mention_author TEXT,
    status TEXT NOT NULL,           -- judged | declined | error
    verdict_json TEXT,              -- saída completa do juiz
    reply_tweet_id TEXT,            -- id do tweet de resposta, se postado
    thread_json TEXT,               -- thread capturada (para o site depois)
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS state (
    key TEXT PRIMARY KEY,
    value TEXT
);
CREATE TABLE IF NOT EXISTS scores (
    user_id TEXT PRIMARY KEY,
    username TEXT,
    balance INTEGER NOT NULL,
    updated_at TEXT
);
CREATE TABLE IF NOT EXISTS ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    username TEXT,
    delta INTEGER NOT NULL,
    reason TEXT NOT NULL,
    conversation_id TEXT,
    created_at TEXT NOT NULL
);
"""

START_BALANCE = 1000


class Store:
    def __init__(self, db_path: str):
        self.conn = sqlite3.connect(db_path)
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    # --- estado do poller ---
    def get_since_id(self) -> str | None:
        row = self.conn.execute(
            "SELECT value FROM state WHERE key = 'since_id'"
        ).fetchone()
        return row[0] if row else None

    def set_since_id(self, since_id: str) -> None:
        self.conn.execute(
            "INSERT INTO state (key, value) VALUES ('since_id', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (since_id,),
        )
        self.conn.commit()

    # --- casos ---
    def case_exists(self, conversation_id: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM cases WHERE conversation_id = ?", (conversation_id,)
        ).fetchone()
        return row is not None

    def save_case(
        self,
        conversation_id: str,
        mention_tweet_id: str,
        mention_author: str | None,
        status: str,
        verdict: dict | None = None,
        reply_tweet_id: str | None = None,
        thread: list[dict] | None = None,
    ) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO cases (conversation_id, mention_tweet_id, "
            "mention_author, status, verdict_json, reply_tweet_id, thread_json, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                conversation_id,
                mention_tweet_id,
                mention_author,
                status,
                json.dumps(verdict, ensure_ascii=False) if verdict else None,
                reply_tweet_id,
                json.dumps(thread, ensure_ascii=False) if thread else None,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        self.conn.commit()

    # --- pontuação ---
    def get_balance(self, user_id: str, username: str | None = None) -> int:
        row = self.conn.execute(
            "SELECT balance FROM scores WHERE user_id = ?", (user_id,)
        ).fetchone()
        if row:
            return row[0]
        self.conn.execute(
            "INSERT INTO scores (user_id, username, balance, updated_at) VALUES (?, ?, ?, ?)",
            (user_id, username, START_BALANCE, datetime.now(timezone.utc).isoformat()),
        )
        self.conn.commit()
        return START_BALANCE

    def adjust_score(
        self,
        user_id: str,
        username: str | None,
        delta: int,
        reason: str,
        conversation_id: str | None = None,
    ) -> int:
        """Aplica delta ao saldo (criando a conta se preciso) e registra no ledger."""
        self.get_balance(user_id, username)  # garante a conta
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            "UPDATE scores SET balance = balance + ?, username = COALESCE(?, username), "
            "updated_at = ? WHERE user_id = ?",
            (delta, username, now, user_id),
        )
        self.conn.execute(
            "INSERT INTO ledger (user_id, username, delta, reason, conversation_id, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, username, delta, reason, conversation_id, now),
        )
        self.conn.commit()
        row = self.conn.execute(
            "SELECT balance FROM scores WHERE user_id = ?", (user_id,)
        ).fetchone()
        return row[0]

    def stats(self) -> dict:
        rows = self.conn.execute(
            "SELECT status, COUNT(*) FROM cases GROUP BY status"
        ).fetchall()
        return dict(rows)
