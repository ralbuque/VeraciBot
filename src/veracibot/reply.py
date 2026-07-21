"""Formata o veredito como reply de até 280 caracteres."""
from __future__ import annotations

MAX_LEN = 280

FACT_LABELS = {
    "verdadeiro": "✅ Verdadeiro",
    "falso": "❌ Falso",
    "parcialmente_verdadeiro": "⚠️ Parcialmente verdadeiro",
    "indeterminado": "❓ Indeterminado",
}


def format_reply(verdict: dict, scores: list | None = None) -> str:
    """Monta o reply; `scores` = [(username, delta, saldo)] do sistema de pontos."""
    if not verdict.get("julgavel"):
        text = "⚖️ Caso arquivado: " + (
            verdict.get("motivo_recusa") or "não identifiquei uma disputa julgável nesta thread."
        )
        return _compose(text, scores)

    curto = verdict.get("veredito_curto") or verdict.get("justificativa", "")

    if verdict.get("tipo_caso") == "fact_check":
        label = FACT_LABELS.get(
            verdict.get("veredito_fatual") or "indeterminado",
            FACT_LABELS["indeterminado"],
        )
        return _compose(f"{label}. {curto}", scores)

    # disputa
    vencedor = verdict.get("vencedor")
    if vencedor == "empate":
        header = "⚖️ Veredito: empate. "
    elif vencedor:
        header = f"⚖️ Veredito: @{vencedor.lstrip('@')} tem razão. "
    else:
        header = "⚖️ Veredito: "
    return _compose(header + curto, scores)


def format_scoreboard(scores: list) -> str:
    parts = [f"@{u} {'+' if d > 0 else ''}{d} ({s} pts)" for u, d, s in scores]
    return "📊 " + " · ".join(parts)


def _compose(text: str, scores: list | None) -> str:
    if not scores:
        return _trim(text, MAX_LEN)
    placar = format_scoreboard(scores)
    budget = MAX_LEN - len(placar) - 1  # 1 = quebra de linha
    return _trim(text, max(budget, 40)) + "\n" + placar


def _trim(text: str, limit: int = MAX_LEN) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"
