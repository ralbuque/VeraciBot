"""Banco do site (escrita): usuários e escritórios de advocacia parceiros.

Usa o mesmo SQLite do bot, com WAL para convivência de escritas.
O admin é criado no startup a partir de ADMIN_EMAIL/ADMIN_PASSWORD no .env.
"""
from __future__ import annotations

import hashlib
import os
import sqlite3
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv()

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE NOT NULL,
    pw_salt TEXT NOT NULL,
    pw_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'firm',   -- firm | admin
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS firms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER UNIQUE NOT NULL,
    name TEXT NOT NULL,
    oab TEXT,
    uf TEXT,
    cidade TEXT,
    areas TEXT,
    contato TEXT,
    status TEXT NOT NULL DEFAULT 'pendente',   -- pendente | aprovado | inativo
    created_at TEXT NOT NULL
);
"""


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(os.environ.get("DB_PATH", "veracibot.db"), timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def init() -> None:
    conn = _db()
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()
    email = os.environ.get("ADMIN_EMAIL", "").strip()
    password = os.environ.get("ADMIN_PASSWORD", "").strip()
    if email and password and not get_user_by_email(email):
        create_user(email, password, role="admin")


def _hash(password: str, salt_hex: str) -> str:
    return hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex),
                          n=16384, r=8, p=1).hex()


# --- usuários ---
def create_user(email: str, password: str, role: str = "firm") -> int | None:
    salt = os.urandom(16).hex()
    conn = _db()
    try:
        cur = conn.execute(
            "INSERT INTO users (email, pw_salt, pw_hash, role, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (email.lower().strip(), salt, _hash(password, salt), role, _now()),
        )
        conn.commit()
        return cur.lastrowid
    except sqlite3.IntegrityError:
        return None
    finally:
        conn.close()


def get_user(user_id: int) -> dict | None:
    conn = _db()
    try:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_user_by_email(email: str) -> dict | None:
    conn = _db()
    try:
        row = conn.execute(
            "SELECT * FROM users WHERE email = ?", (email.lower().strip(),)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def verify_user(email: str, password: str) -> dict | None:
    user = get_user_by_email(email)
    if not user:
        return None
    if _hash(password, user["pw_salt"]) != user["pw_hash"]:
        return None
    return user


# --- escritórios ---
def create_firm(user_id: int, data: dict) -> int:
    conn = _db()
    try:
        cur = conn.execute(
            "INSERT INTO firms (user_id, name, oab, uf, cidade, areas, contato, "
            "status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, 'pendente', ?)",
            (user_id, data.get("name", ""), data.get("oab", ""),
             (data.get("uf") or "").upper()[:2], data.get("cidade", ""),
             data.get("areas", ""), data.get("contato", ""), _now()),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def update_firm(user_id: int, data: dict) -> None:
    conn = _db()
    try:
        conn.execute(
            "UPDATE firms SET name = ?, oab = ?, uf = ?, cidade = ?, areas = ?, "
            "contato = ? WHERE user_id = ?",
            (data.get("name", ""), data.get("oab", ""),
             (data.get("uf") or "").upper()[:2], data.get("cidade", ""),
             data.get("areas", ""), data.get("contato", ""), user_id),
        )
        conn.commit()
    finally:
        conn.close()


def get_firm_by_user(user_id: int) -> dict | None:
    conn = _db()
    try:
        row = conn.execute(
            "SELECT * FROM firms WHERE user_id = ?", (user_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_firms(status: str | None = None, uf: str | None = None) -> list[dict]:
    sql, args = "SELECT * FROM firms", []
    conds = []
    if status:
        conds.append("status = ?")
        args.append(status)
    if uf:
        conds.append("uf = ?")
        args.append(uf.upper())
    if conds:
        sql += " WHERE " + " AND ".join(conds)
    sql += " ORDER BY uf, name"
    conn = _db()
    try:
        return [dict(r) for r in conn.execute(sql, args).fetchall()]
    finally:
        conn.close()


def set_firm_status(firm_id: int, status: str) -> None:
    conn = _db()
    try:
        conn.execute("UPDATE firms SET status = ? WHERE id = ?", (status, firm_id))
        conn.commit()
    finally:
        conn.close()
