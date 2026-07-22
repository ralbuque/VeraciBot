"""Formata o veredito como reply de até 280 caracteres."""
from __future__ import annotations

MAX_LEN = 280

FACT_LABELS = {
    "verdadeiro": "✅ Verdadeiro",
    "falso": "❌ Falso",
    "parcialmente_verdadeiro": "⚠️ Parcialmente verdadeiro",
    "indeterminado": "❓ Indeterminado",
}


JUSTICE_LINE = "⚠️ Caso sério: recomendamos procurar a justiça."


def composition_line(tipo: str | None, loser: str, winner: str) -> str:
    if tipo == "fact_check":
        return f"🤝 @{loser}: retratação pública devolve 8 pts (@{winner} confirma, 7 dias)"
    return f"🤝 @{loser}: desculpas + reparação a @{winner} devolvem 8 pts (7 dias)"


def format_reply(verdict: dict, scores: list | None = None, extra: str | None = None) -> str:
    """Monta o reply; `scores` = [(username, delta, saldo)]; `extra` = linha de composição."""
    if not verdict.get("julgavel"):
        text = "⚖️ Caso arquivado: " + (
            verdict.get("motivo_recusa") or "não identifiquei uma disputa julgável nesta thread."
        )
        return _compose(text, scores, extra)

    curto = verdict.get("veredito_curto") or verdict.get("justificativa", "")

    if verdict.get("tipo_caso") == "fact_check":
        label = FACT_LABELS.get(
            verdict.get("veredito_fatual") or "indeterminado",
            FACT_LABELS["indeterminado"],
        )
        return _compose(f"{label}. {curto}", scores, extra)

    # disputa
    vencedor = verdict.get("vencedor")
    if vencedor == "empate":
        header = "⚖️ Veredito: empate. "
    elif vencedor:
        header = f"⚖️ Veredito: @{vencedor.lstrip('@')} tem razão. "
    else:
        header = "⚖️ Veredito: "
    return _compose(header + curto, scores, extra)


def format_scoreboard(scores: list) -> str:
    parts = [f"@{u} {'+' if d > 0 else ''}{d} ({s} pts)" for u, d, s in scores]
    return "📊 " + " · ".join(parts)


def _compose(text: str, scores: list | None, extra: str | None = None) -> str:
    tail = ""
    if scores:
        tail += "\n" + format_scoreboard(scores)
    if extra:
        tail += "\n" + extra
    if not tail:
        return _trim(text, MAX_LEN)
    budget = MAX_LEN - len(tail)
    return _trim(_trim(text, max(budget, 40)) + tail, MAX_LEN)


def _trim(text: str, limit: int = MAX_LEN) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"
