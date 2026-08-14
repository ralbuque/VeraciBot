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
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from . import webdb
from .i18n import T

load_dotenv()

BASE = Path(__file__).parent
app = FastAPI(title="VeraciBot — The Internet Tribunal")
app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ.get("WEB_SECRET", "troque-este-segredo"),
    same_site="lax",
)
app.mount("/static", StaticFiles(directory=str(BASE / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE / "templates"))

webdb.init()

PATHS = {
    "pt": {"home": "/", "ranking": "/ranking", "cases": "/casos", "case_base": "/caso",
           "lawyers": "/advogados"},
    "en": {"home": "/en", "ranking": "/en/ranking", "cases": "/en/cases",
           "case_base": "/en/case", "lawyers": "/en/lawyers"},
}

FIRM_FIELDS = ("name", "oab", "uf", "cidade", "areas", "contato")

PROMO = os.environ.get("PROMO_ENABLED", "false").lower() == "true"


def _current_user(request: Request) -> dict | None:
    uid = request.session.get("uid")
    return webdb.get_user(uid) if uid else None


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


def _case_dict(r, placar: list) -> dict:
    v = json.loads(r["verdict_json"] or "{}")
    return {
        "id": r["conversation_id"],
        "status": r["status"],
        "date": (r["created_at"] or "")[:10],
        "tipo": v.get("tipo_caso"),
        "julgavel": bool(v.get("julgavel")),
        "resumo": v.get("resumo_disputa") or "",
        "justificativa": v.get("justificativa") or v.get("motivo_recusa") or "",
        "vencedor": v.get("vencedor"),
        "fatual": v.get("veredito_fatual"),
        "afirmacao": v.get("afirmacao"),
        "gravidade": v.get("gravidade"),
        "contradicao": v.get("contradicao"),
        "onus": v.get("onus"),
        "fato_a_provar": v.get("fato_a_provar"),
        "url": f"https://x.com/i/status/{r['conversation_id']}",
        "placar": sorted(placar, key=lambda x: -x[1]),
    }


def _cases(limit: int = 50) -> list[dict]:
    rows = _query(
        "SELECT * FROM cases WHERE status IN ('judged','declined','aguardando_provas') "
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
    cases = [_case_dict(r, dmap.get(r["conversation_id"], [])) for r in rows]
    if PROMO:  # modo promoção: o site exibe só checagens de fato
        cases = [c for c in cases if c["tipo"] == "fact_check" or not c["julgavel"]]
    return cases


def _case_detail(conversation_id: str) -> dict | None:
    rows = _query("SELECT * FROM cases WHERE conversation_id = ?", (conversation_id,))
    if not rows:
        return None
    r = rows[0]
    placar = [(x["username"], x["d"]) for x in _query(
        "SELECT username, SUM(delta) AS d FROM ledger WHERE conversation_id = ? "
        "AND reason != 'custo_chamada' GROUP BY username", (conversation_id,))]
    case = _case_dict(r, placar)
    case["thread"] = json.loads(r["thread_json"]) if r["thread_json"] else []
    case["ledger"] = [dict(x) for x in _query(
        "SELECT username, delta, reason, created_at FROM ledger "
        "WHERE conversation_id = ? ORDER BY id", (conversation_id,))]
    comp = _query("SELECT * FROM compositions WHERE conversation_id = ?",
                  (conversation_id,))
    case["composition"] = dict(comp[0]) if comp else None
    ap = _query("SELECT * FROM appeals WHERE conversation_id = ?", (conversation_id,))
    case["appeal"] = dict(ap[0]) if ap else None
    if case["appeal"]:
        votes = _query(
            "SELECT choice_username, COUNT(*) AS n FROM appeal_votes "
            "WHERE conversation_id = ? GROUP BY choice_username", (conversation_id,))
        case["votes"] = {v["choice_username"]: v["n"] for v in votes}
    return case


def _render(request: Request, template: str, lang: str, alt: str, **ctx):
    return templates.TemplateResponse(
        request=request,
        name=template,
        context={
            "t": T[lang],
            "lang": lang,
            "p": PATHS[lang],
            "alt": alt,
            "promo": PROMO,
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


@app.get("/advogados")
def lawyers_pt(request: Request, uf: str = ""):
    firms = webdb.list_firms(status="aprovado", uf=uf or None)
    return _render(request, "advogados.html", "pt", "/en/lawyers",
                   firms=firms, uf=uf.upper())


@app.get("/en/lawyers")
def lawyers_en(request: Request, uf: str = ""):
    firms = webdb.list_firms(status="aprovado", uf=uf or None)
    return _render(request, "advogados.html", "en", "/advogados",
                   firms=firms, uf=uf.upper())


# --- autenticação e área logada (pt) ---
@app.get("/login")
def login_page(request: Request, msg: str = ""):
    return _render(request, "login.html", "pt", "/", msg=msg)


@app.post("/login")
async def login_submit(request: Request):
    form = await request.form()
    user = webdb.verify_user(form.get("email", ""), form.get("password", ""))
    if not user:
        return _render(request, "login.html", "pt", "/", msg="E-mail ou senha inválidos.")
    request.session["uid"] = user["id"]
    return RedirectResponse("/admin" if user["role"] == "admin" else "/painel",
                            status_code=303)


@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/", status_code=303)


@app.get("/registro")
def register_page(request: Request):
    return _render(request, "registro.html", "pt", "/", msg="")


@app.post("/registro")
async def register_submit(request: Request):
    form = await request.form()
    email = (form.get("email") or "").strip()
    password = form.get("password") or ""
    if not email or len(password) < 8:
        return _render(request, "registro.html", "pt", "/",
                       msg="Informe e-mail válido e senha com 8+ caracteres.")
    uid = webdb.create_user(email, password)
    if not uid:
        return _render(request, "registro.html", "pt", "/",
                       msg="Este e-mail já está cadastrado.")
    webdb.create_firm(uid, {k: form.get(k, "") for k in FIRM_FIELDS})
    request.session["uid"] = uid
    return RedirectResponse("/painel", status_code=303)


@app.get("/painel")
def panel_page(request: Request, msg: str = ""):
    user = _current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    firm = webdb.get_firm_by_user(user["id"])
    return _render(request, "painel.html", "pt", "/", firm=firm, user=user, msg=msg)


@app.post("/painel")
async def panel_submit(request: Request):
    user = _current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    form = await request.form()
    webdb.update_firm(user["id"], {k: form.get(k, "") for k in FIRM_FIELDS})
    firm = webdb.get_firm_by_user(user["id"])
    return _render(request, "painel.html", "pt", "/", firm=firm, user=user,
                   msg="Dados salvos.")


@app.get("/admin")
def admin_page(request: Request):
    user = _current_user(request)
    if not user or user["role"] != "admin":
        return RedirectResponse("/login", status_code=303)
    return _render(request, "admin.html", "pt", "/",
                   firms=webdb.list_firms(), user=user)


@app.post("/admin/firm/{firm_id}")
async def admin_firm_status(request: Request, firm_id: int):
    user = _current_user(request)
    if not user or user["role"] != "admin":
        return RedirectResponse("/login", status_code=303)
    form = await request.form()
    status = form.get("status")
    if status in ("pendente", "aprovado", "inativo"):
        webdb.set_firm_status(firm_id, status)
    return RedirectResponse("/admin", status_code=303)


@app.get("/caso/{conversation_id}")
def case_pt(request: Request, conversation_id: str):
    case = _case_detail(conversation_id)
    if not case:
        return _render(request, "casos.html", "pt", "/en/cases", cases=_cases())
    return _render(request, "caso.html", "pt", f"/en/case/{conversation_id}", case=case)


@app.get("/en/case/{conversation_id}")
def case_en(request: Request, conversation_id: str):
    case = _case_detail(conversation_id)
    if not case:
        return _render(request, "casos.html", "en", "/casos", cases=_cases())
    return _render(request, "caso.html", "en", f"/caso/{conversation_id}", case=case)
