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
CREATE TABLE IF NOT EXISTS members (
    username TEXT PRIMARY KEY,      -- lowercase, sem @
    user_id TEXT,
    invited_by TEXT,
    invites_left INTEGER NOT NULL DEFAULT 5,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS rejected_notices (
    username TEXT PRIMARY KEY,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS compositions (
    conversation_id TEXT PRIMARY KEY,
    tipo TEXT,
    loser_id TEXT NOT NULL,
    loser_username TEXT,
    winner_id TEXT NOT NULL,
    winner_username TEXT,
    deadline TEXT NOT NULL,
    status TEXT NOT NULL,           -- pendente | cumprida | expirada
    created_at TEXT NOT NULL,
    resolved_at TEXT
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

    # --- estado genérico ---
    def get_state(self, key: str) -> str | None:
        row = self.conn.execute(
            "SELECT value FROM state WHERE key = ?", (key,)
        ).fetchone()
        return row[0] if row else None

    def set_state(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT INTO state (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        self.conn.commit()

    # --- membros (sistema de convites) ---
    def get_member(self, username: str) -> dict | None:
        row = self.conn.execute(
            "SELECT username, user_id, invited_by, invites_left FROM members "
            "WHERE username = ?", (username.lower(),)
        ).fetchone()
        if not row:
            return None
        return {"username": row[0], "user_id": row[1],
                "invited_by": row[2], "invites_left": row[3]}

    def is_member(self, username: str) -> bool:
        return self.get_member(username) is not None

    def add_member(self, username: str, invited_by: str,
                   user_id: str | None = None, invites: int = 5) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO members (username, user_id, invited_by, "
            "invites_left, created_at) VALUES (?, ?, ?, ?, ?)",
            (username.lower(), user_id, invited_by.lower(), invites,
             datetime.now(timezone.utc).isoformat()),
        )
        self.conn.commit()

    def use_invite(self, username: str) -> int:
        """Consome 1 convite; retorna quantos restam."""
        self.conn.execute(
            "UPDATE members SET invites_left = invites_left - 1 "
            "WHERE username = ? AND invites_left > 0", (username.lower(),)
        )
        self.conn.commit()
        m = self.get_member(username)
        return m["invites_left"] if m else 0

    def set_member_user_id(self, username: str, user_id: str) -> None:
        self.conn.execute(
            "UPDATE members SET user_id = ? WHERE username = ?",
            (user_id, username.lower()),
        )
        self.conn.commit()

    def was_rejection_notified(self, username: str) -> bool:
        return self.conn.execute(
            "SELECT 1 FROM rejected_notices WHERE username = ?",
            (username.lower(),),
        ).fetchone() is not None

    def mark_rejection_notified(self, username: str) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO rejected_notices (username, created_at) VALUES (?, ?)",
            (username.lower(), datetime.now(timezone.utc).isoformat()),
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

    # --- composição ---
    def create_composition(
        self,
        conversation_id: str,
        tipo: str | None,
        loser_id: str,
        loser_username: str,
        winner_id: str,
        winner_username: str,
        deadline: str,
    ) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO compositions (conversation_id, tipo, loser_id, "
            "loser_username, winner_id, winner_username, deadline, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 'pendente', ?)",
            (conversation_id, tipo, loser_id, loser_username, winner_id,
             winner_username, deadline, datetime.now(timezone.utc).isoformat()),
        )
        self.conn.commit()

    def get_pending_composition(self, conversation_id: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM compositions WHERE conversation_id = ? AND status = 'pendente'",
            (conversation_id,),
        ).fetchone()
        if not row:
            return None
        cols = [d[0] for d in self.conn.execute(
            "SELECT * FROM compositions LIMIT 0").description]
        return dict(zip(cols, row))

    def resolve_composition(self, conversation_id: str, status: str) -> None:
        self.conn.execute(
            "UPDATE compositions SET status = ?, resolved_at = ? WHERE conversation_id = ?",
            (status, datetime.now(timezone.utc).isoformat(), conversation_id),
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
