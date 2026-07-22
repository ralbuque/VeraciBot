"""Site público do VeraciBot: landing, ranking e casos julgados.

Lê o SQLite do bot em modo somente-leitura. Rodar com:
    uvicorn src.veracibot.web.app:app --port 8000
"""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .i18n import T

load_dotenv()

BASE = Path(__file__).parent
app = FastAPI(title="VeraciBot — The Internet Tribunal")
app.mount("/static", StaticFiles(directory=str(BASE / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE / "templates"))

PATHS = {
    "pt": {"home": "/", "ranking": "/ranking", "cases": "/casos"},
    "en": {"home": "/en", "ranking": "/en/ranking", "cases": "/en/cases"},
}


def _query(sql: str, args: tuple = ()) -> list[sqlite3.Row]:
    path = os.environ.get("DB_PATH", "veracibot.db")
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    except sqlite3.OperationalError:
        return []  # banco ainda não existe
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(sql, args).fetchall()
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()


def _stats() -> dict:
    rows = _query("SELECT status, verdict_json FROM cases WHERE status IN ('judged','declined')")
    verdicts = [json.loads(r["verdict_json"]) for r in rows if r["verdict_json"]]
    judged = [v for v in verdicts if v.get("julgavel")]
    fact = sum(1 for v in judged if v.get("tipo_caso") == "fact_check")
    users = _query("SELECT COUNT(*) AS c FROM scores")
    return {
        "cases": len(rows),
        "fact": fact,
        "disputes": len(judged) - fact,
        "users": users[0]["c"] if users else 0,
    }


def _leaderboard(limit: int = 100) -> list[dict]:
    rows = _query(
        "SELECT username, balance FROM scores ORDER BY balance DESC, username LIMIT ?",
        (limit,),
    )
    return [dict(r) for r in rows]


def _cases(limit: int = 50) -> list[dict]:
    rows = _query(
        "SELECT * FROM cases WHERE status IN ('judged','declined') "
        "ORDER BY created_at DESC LIMIT ?",
        (limit,),
    )
    deltas = _query(
        "SELECT conversation_id, username, SUM(delta) AS d FROM ledger "
        "WHERE reason != 'custo_chamada' GROUP BY conversation_id, username"
    )
    dmap: dict[str, list] = {}
    for r in deltas:
        dmap.setdefault(r["conversation_id"], []).append((r["username"], r["d"]))

    cases = []
    for r in rows:
        v = json.loads(r["verdict_json"] or "{}")
        cases.append(
            {
                "date": (r["created_at"] or "")[:10],
                "tipo": v.get("tipo_caso"),
                "julgavel": bool(v.get("julgavel")),
                "resumo": v.get("resumo_disputa") or "",
                "justificativa": v.get("justificativa") or v.get("motivo_recusa") or "",
                "vencedor": v.get("vencedor"),
                "fatual": v.get("veredito_fatual"),
                "afirmacao": v.get("afirmacao"),
                "url": f"https://x.com/i/status/{r['conversation_id']}",
                "placar": sorted(dmap.get(r["conversation_id"], []), key=lambda x: -x[1]),
            }
        )
    return cases


def _render(request: Request, template: str, lang: str, alt: str, **ctx):
    return templates.TemplateResponse(
        request=request,
        name=template,
        context={
            "t": T[lang],
            "lang": lang,
            "p": PATHS[lang],
            "alt": alt,
            **ctx,
        },
    )


@app.get("/")
def index_pt(request: Request):
    return _render(request, "index.html", "pt", "/en", stats=_stats())


@app.get("/en")
def index_en(request: Request):
    return _render(request, "index.html", "en", "/", stats=_stats())


@app.get("/ranking")
def ranking_pt(request: Request):
    return _render(request, "ranking.html", "pt", "/en/ranking", rows=_leaderboard())


@app.get("/en/ranking")
def ranking_en(request: Request):
    return _render(request, "ranking.html", "en", "/ranking", rows=_leaderboard())


@app.get("/casos")
def cases_pt(request: Request):
    return _render(request, "casos.html", "pt", "/en/cases", cases=_cases())


@app.get("/en/cases")
def cases_en(request: Request):
    return _render(request, "casos.html", "en", "/casos", cases=_cases())
