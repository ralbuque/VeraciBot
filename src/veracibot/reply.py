"""Formata o veredito como reply de até 280 caracteres (contagem ponderada do X)."""
from __future__ import annotations

MAX_LEN = 278  # margem de segurança sob o limite de 280

# Faixas Unicode que valem 1 na contagem do X (twitter-text); o resto vale 2.
_LIGHT_RANGES = ((0, 4351), (8192, 8205), (8208, 8223), (8242, 8247))


def x_len(text: str) -> int:
    """Comprimento como o X conta: latinos/acentos = 1, emoji/CJK = 2 (conservador)."""
    total = 0
    for ch in text:
        cp = ord(ch)
        total += 1 if any(a <= cp <= b for a, b in _LIGHT_RANGES) else 2
    return total

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


def format_reply(
    verdict: dict,
    scores: list | None = None,
    extra: str | None = None,
    max_len: int = MAX_LEN,
) -> str:
    """Monta o reply; `scores` = [(username, delta, saldo)]; `extra` = linha de composição.

    Com `max_len` alto (conta Premium), usa a justificativa completa em vez do
    veredito curto.
    """
    if not verdict.get("julgavel"):
        text = "⚖️ Caso arquivado: " + (
            verdict.get("motivo_recusa") or "não identifiquei uma disputa julgável nesta thread."
        )
        return _compose(text, scores, extra, max_len)

    curto = verdict.get("veredito_curto") or verdict.get("justificativa", "")
    if max_len > 400:
        curto = verdict.get("justificativa") or curto

    if verdict.get("tipo_caso") == "fact_check":
        label = FACT_LABELS.get(
            verdict.get("veredito_fatual") or "indeterminado",
            FACT_LABELS["indeterminado"],
        )
        return _compose(f"{label}. {curto}", scores, extra, max_len)

    # disputa
    vencedor = verdict.get("vencedor")
    if vencedor == "empate":
        header = "⚖️ Veredito: empate. "
    elif vencedor:
        header = f"⚖️ Veredito: @{vencedor.lstrip('@')} tem razão. "
    else:
        header = "⚖️ Veredito: "
    return _compose(header + curto, scores, extra, max_len)


def format_scoreboard(scores: list) -> str:
    parts = [f"@{u} {'+' if d > 0 else ''}{d} ({s} pts)" for u, d, s in scores]
    return "📊 " + " · ".join(parts)


def _compose(text: str, scores: list | None, extra: str | None = None,
             max_len: int = MAX_LEN) -> str:
    tail = ""
    if scores:
        tail += "\n\n" + format_scoreboard(scores) if max_len > 400 else "\n" + format_scoreboard(scores)
    if extra:
        tail += "\n" + extra
    if not tail:
        return _trim(text, max_len)
    budget = max_len - x_len(tail)
    return _trim(_trim(text, max(budget, 40)) + tail, max_len)


def _trim(text: str, limit: int = MAX_LEN) -> str:
    """Corta pelo comprimento ponderado do X, adicionando reticências."""
    if x_len(text) <= limit:
        return text
    out, total = [], 0
    for ch in text:
        w = 1 if any(a <= ord(ch) <= b for a, b in _LIGHT_RANGES) else 2
        if total + w > limit - 2:  # reserva para o "…" (peso 2)
            break
        out.append(ch)
        total += w
    return "".join(out).rstrip() + "…"
