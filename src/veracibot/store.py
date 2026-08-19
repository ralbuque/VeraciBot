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
CREATE TABLE IF NOT EXISTS appeals (
    conversation_id TEXT PRIMARY KEY,
    appellant_id TEXT NOT NULL,
    appellant_username TEXT,
    opponent_username TEXT,
    poll_tweet_id TEXT NOT NULL,
    ends_at TEXT NOT NULL,
    status TEXT NOT NULL,           -- aberta | mantida | reformada
    created_at TEXT NOT NULL,
    resolved_at TEXT
);
CREATE TABLE IF NOT EXISTS outbox (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL,
    in_reply_to TEXT,               -- NULL = tweet avulso
    attempts INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    sent_at TEXT
);
CREATE TABLE IF NOT EXISTS promo_participants (
    user_id TEXT PRIMARY KEY,
    username TEXT,
    joined_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS appeal_votes (
    conversation_id TEXT NOT NULL,
    voter_id TEXT NOT NULL,
    voter_username TEXT,
    choice_username TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (conversation_id, voter_id)
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

    # --- limites anti-farming / anti-spam ---
    def calls_in_window(self, user_id: str, since_iso: str) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) FROM ledger WHERE user_id = ? "
            "AND reason = 'custo_chamada' AND created_at >= ?",
            (user_id, since_iso),
        ).fetchone()
        return row[0]

    def pair_scored_cases(self, caller_id: str, target_id: str,
                          since_iso: str) -> int:
        """Casos pontuados desse chamador em que o alvo perdeu/ganhou pontos."""
        row = self.conn.execute(
            "SELECT COUNT(DISTINCT l1.conversation_id) FROM ledger l1 "
            "JOIN ledger l2 ON l2.conversation_id = l1.conversation_id "
            "WHERE l1.user_id = ? AND l1.reason = 'custo_chamada' "
            "AND l1.created_at >= ? AND l2.user_id = ? "
            "AND l2.reason LIKE 'fact_check:%'",
            (caller_id, since_iso, target_id),
        ).fetchone()
        return row[0]

    def false_claim_count(self, user_id: str) -> int:
        """Quantas afirmações desse autor já foram julgadas falsas."""
        row = self.conn.execute(
            "SELECT COUNT(*) FROM ledger WHERE user_id = ? "
            "AND reason = 'fact_check:falso' AND delta < 0",
            (user_id,),
        ).fetchone()
        return row[0]

    def notice_once(self, key: str) -> bool:
        """True apenas na primeira vez que a chave é vista (para avisos únicos)."""
        if self.get_state("notice:" + key):
            return False
        self.set_state("notice:" + key, "1")
        return True

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
    def get_case(self, conversation_id: str) -> dict | None:
        row = self.conn.execute(
            "SELECT conversation_id, mention_tweet_id, mention_author, status, "
            "verdict_json, reply_tweet_id FROM cases WHERE conversation_id = ?",
            (conversation_id,)
        ).fetchone()
        if not row:
            return None
        return {
            "conversation_id": row[0],
            "mention_tweet_id": row[1],
            "mention_author": row[2],
            "status": row[3],
            "verdict": json.loads(row[4]) if row[4] else {},
            "reply_tweet_id": row[5],
        }

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

    def expired_pending_compositions(self, now_iso: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT conversation_id FROM compositions "
            "WHERE status = 'pendente' AND deadline < ?", (now_iso,)
        ).fetchall()
        return [self.get_pending_composition(r[0]) for r in rows]

    def resolve_composition(self, conversation_id: str, status: str) -> None:
        self.conn.execute(
            "UPDATE compositions SET status = ?, resolved_at = ? WHERE conversation_id = ?",
            (status, datetime.now(timezone.utc).isoformat(), conversation_id),
        )
        self.conn.commit()

    # --- outbox (escritas pendentes) ---
    def enqueue_post(self, text: str, in_reply_to: str | None = None) -> None:
        self.conn.execute(
            "INSERT INTO outbox (text, in_reply_to, created_at) VALUES (?, ?, ?)",
            (text, in_reply_to, datetime.now(timezone.utc).isoformat()),
        )
        self.conn.commit()

    def pending_outbox(self, limit: int = 5) -> list[dict]:
        rows = self.conn.execute(
            "SELECT id, text, in_reply_to FROM outbox "
            "WHERE sent_at IS NULL AND attempts < 10 ORDER BY id LIMIT ?",
            (limit,),
        ).fetchall()
        return [{"id": r[0], "text": r[1], "in_reply_to": r[2]} for r in rows]

    def mark_outbox_sent(self, outbox_id: int) -> None:
        self.conn.execute(
            "UPDATE outbox SET sent_at = ? WHERE id = ?",
            (datetime.now(timezone.utc).isoformat(), outbox_id),
        )
        self.conn.commit()

    def mark_outbox_failed(self, outbox_id: int) -> None:
        self.conn.execute(
            "UPDATE outbox SET attempts = 99 WHERE id = ?", (outbox_id,)
        )
        self.conn.commit()

    def bump_outbox_attempt(self, outbox_id: int) -> None:
        self.conn.execute(
            "UPDATE outbox SET attempts = attempts + 1 WHERE id = ?", (outbox_id,)
        )
        self.conn.commit()

    # --- promoção ---
    def add_participant(self, user_id: str, username: str) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO promo_participants (user_id, username, joined_at) "
            "VALUES (?, ?, ?)",
            (user_id, username, datetime.now(timezone.utc).isoformat()),
        )
        self.conn.commit()

    def is_participant(self, user_id: str) -> bool:
        return self.conn.execute(
            "SELECT 1 FROM promo_participants WHERE user_id = ?", (user_id,)
        ).fetchone() is not None

    def participants(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT user_id, username FROM promo_participants"
        ).fetchall()
        return [{"user_id": r[0], "username": r[1]} for r in rows]

    # --- recursos (apelação) ---
    def create_appeal(self, conversation_id: str, appellant_id: str,
                      appellant_username: str, opponent_username: str,
                      poll_tweet_id: str, ends_at: str) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO appeals (conversation_id, appellant_id, "
            "appellant_username, opponent_username, poll_tweet_id, ends_at, "
            "status, created_at) VALUES (?, ?, ?, ?, ?, ?, 'aberta', ?)",
            (conversation_id, appellant_id, appellant_username, opponent_username,
             poll_tweet_id, ends_at, datetime.now(timezone.utc).isoformat()),
        )
        self.conn.commit()

    def get_appeal(self, conversation_id: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM appeals WHERE conversation_id = ?", (conversation_id,)
        ).fetchone()
        return self._appeal_dict(row)

    def open_appeals(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM appeals WHERE status = 'aberta'"
        ).fetchall()
        return [self._appeal_dict(r) for r in rows]

    def _appeal_dict(self, row) -> dict | None:
        if not row:
            return None
        cols = [d[0] for d in self.conn.execute(
            "SELECT * FROM appeals LIMIT 0").description]
        return dict(zip(cols, row))

    def record_vote(self, conversation_id: str, voter_id: str,
                    voter_username: str, choice_username: str) -> None:
        """Registra (ou troca) o voto de um membro no recurso."""
        self.conn.execute(
            "INSERT OR REPLACE INTO appeal_votes (conversation_id, voter_id, "
            "voter_username, choice_username, created_at) VALUES (?, ?, ?, ?, ?)",
            (conversation_id, voter_id, voter_username, choice_username.lower(),
             datetime.now(timezone.utc).isoformat()),
        )
        self.conn.commit()

    def count_votes(self, conversation_id: str) -> dict:
        rows = self.conn.execute(
            "SELECT choice_username, COUNT(*) FROM appeal_votes "
            "WHERE conversation_id = ? GROUP BY choice_username",
            (conversation_id,),
        ).fetchall()
        return dict(rows)

    def resolve_appeal(self, conversation_id: str, status: str) -> None:
        self.conn.execute(
            "UPDATE appeals SET status = ?, resolved_at = ? WHERE conversation_id = ?",
            (status, datetime.now(timezone.utc).isoformat(), conversation_id),
        )
        self.conn.commit()

    def case_deltas(self, conversation_id: str) -> list[dict]:
        """Somatório de pontos do julgamento (sem custos/estornos) por usuário."""
        rows = self.conn.execute(
            "SELECT user_id, username, SUM(delta) AS total FROM ledger "
            "WHERE conversation_id = ? AND (reason LIKE 'fact_check:%' "
            "OR reason LIKE 'disputa:%' OR reason = 'reforma_recurso') "
            "GROUP BY user_id", (conversation_id,)
        ).fetchall()
        return [{"user_id": r[0], "username": r[1], "total": r[2]} for r in rows]

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
