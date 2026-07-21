"""Sistema de pontuação do tribunal.

Regras (fact-check):
- Todo handle começa com 1000 pontos.
- Chamar o bot custa 1 ponto (exige saldo >= 1; estornado em erro interno).

Papéis identificados pelo juiz: autor da afirmação (afirma), contestador (se houver)
e a posição do chamador ("afirma" | "contesta" | "neutro").

1) Chamador é PARTE (afirma ou contesta):
   - Chamador certo: +11 (líquido +10, devolve o custo). Chamador errado: -10 (total -11).
   - Outro lado certo: +10. Outro lado errado: -11 (10 por errar + 1 pelo uso do sistema).
2) Chamador NEUTRO (terceiro perguntando quem está certo entre dois que discutem):
   - Chamador: só o custo de 1 ponto.
   - Lado certo: +10. Lado errado: -10.
   - Sem contestador na thread, chamar = contestar (cai na regra 1).
3) Parcialmente verdadeiro / indeterminado / recusado: ninguém ganha nem perde;
   permanece só o custo do chamador.

DISPUTAS seguem a mesma matriz, com vencedor/perdedor no lugar de certo/errado:
- Chamador vence: +11 (líquido +10); perdedor -11.
- Chamador perde: -10 (total -11); vencedor +10.
- Chamador neutro: só o custo; vencedor +10, perdedor -10.
- Empate ou sem vencedor: só o custo do chamador.
"""
from __future__ import annotations

import logging

from .store import Store

log = logging.getLogger(__name__)

CALL_COST = 1


def resolve_user_id(thread: list[dict], username: str) -> str | None:
    """Encontra o author_id de um username dentro da thread capturada."""
    for t in thread:
        if (t.get("author_username") or "").lower() == username.lower():
            return t.get("author_id")
    return None


def _clean(username: str | None) -> str:
    return (username or "").lstrip("@").strip()


def apply_scores(
    store: Store,
    verdict: dict,
    requester_id: str,
    requester_username: str,
    thread: list[dict],
    conversation_id: str,
) -> list[tuple[str, int, int]]:
    """Despacha a pontuação conforme o tipo de caso."""
    if verdict.get("tipo_caso") == "disputa":
        return apply_dispute_scores(
            store, verdict, requester_id, requester_username, thread, conversation_id
        )
    return apply_fact_check_scores(
        store, verdict, requester_id, requester_username, thread, conversation_id
    )


def apply_dispute_scores(
    store: Store,
    verdict: dict,
    requester_id: str,
    requester_username: str,
    thread: list[dict],
    conversation_id: str,
) -> list[tuple[str, int, int]]:
    """Pontuação de disputas: vencedor/perdedor (mesma matriz do fact-check)."""
    if verdict.get("tipo_caso") != "disputa" or not verdict.get("julgavel"):
        return []
    vencedor = _clean(verdict.get("vencedor"))
    if not vencedor or vencedor.lower() == "empate":
        return []

    perdedor = _clean(verdict.get("perdedor"))
    if not perdedor:
        # Fallback: primeira parte listada que não seja o vencedor.
        for parte in verdict.get("partes") or []:
            u = _clean(parte.get("username"))
            if u and u.lower() != vencedor.lower():
                perdedor = u
                break

    venc_id = resolve_user_id(thread, vencedor)
    perd_id = resolve_user_id(thread, perdedor) if perdedor else None
    req = requester_username.lower()

    changes: list[tuple[str | None, str, int]] = []
    if vencedor.lower() == req:
        changes.append((requester_id, requester_username, +11))
        if perdedor:
            changes.append((perd_id, perdedor, -11))
    elif perdedor and perdedor.lower() == req:
        changes.append((requester_id, requester_username, -10))
        changes.append((venc_id, vencedor, +10))
    else:  # chamador neutro
        changes.append((venc_id, vencedor, +10))
        if perdedor:
            changes.append((perd_id, perdedor, -10))

    return _apply(store, changes, f"disputa:{vencedor}", conversation_id)


def apply_fact_check_scores(
    store: Store,
    verdict: dict,
    requester_id: str,
    requester_username: str,
    thread: list[dict],
    conversation_id: str,
) -> list[tuple[str, int, int]]:
    """Aplica a pontuação pós-veredito. Retorna [(username, delta, novo_saldo)].

    O custo da chamada (1 ponto) já deve ter sido debitado antes do julgamento.
    """
    if verdict.get("tipo_caso") != "fact_check" or not verdict.get("julgavel"):
        return []
    vf = verdict.get("veredito_fatual")
    if vf not in ("verdadeiro", "falso"):
        return []  # parcial/indeterminado: neutro

    claim_true = vf == "verdadeiro"
    autor = _clean(verdict.get("autor_afirmacao"))
    contestador = _clean(verdict.get("contestador"))
    autor_id = resolve_user_id(thread, autor) if autor else None
    contest_id = resolve_user_id(thread, contestador) if contestador else None

    req = requester_username.lower()

    # Posição do chamador: identidade na thread tem precedência sobre o juiz.
    if autor and autor.lower() == req:
        posicao = "afirma"
    elif contestador and contestador.lower() == req:
        posicao = "contesta"
    else:
        posicao = verdict.get("posicao_chamador") or "contesta"
    # Neutro sem contestador identificado: chamar = contestar.
    if posicao == "neutro" and not contestador:
        posicao = "contesta"

    changes: list[tuple[str | None, str, int]] = []  # (user_id, username, delta)

    if posicao == "neutro":
        # Terceiro neutro: só paga o custo; os dois lados disputam ±10.
        if autor and autor.lower() != req:
            changes.append((autor_id, autor, +10 if claim_true else -10))
        if contestador and contestador.lower() != req and contestador.lower() != autor.lower():
            changes.append((contest_id, contestador, -10 if claim_true else +10))
    else:
        caller_right = (posicao == "afirma") == claim_true
        changes.append((requester_id, requester_username, +11 if caller_right else -10))
        # Outro lado (se existir e não for o próprio chamador)
        other = contestador if posicao == "afirma" else autor
        other_id = contest_id if posicao == "afirma" else autor_id
        if other and other.lower() != req:
            changes.append((other_id, other, -11 if caller_right else +10))

    return _apply(store, changes, f"fact_check:{vf}", conversation_id)


def _apply(
    store: Store,
    changes: list[tuple[str | None, str, int]],
    reason: str,
    conversation_id: str,
) -> list[tuple[str, int, int]]:
    results = []
    for user_id, username, delta in changes:
        if not user_id:
            log.warning("Sem user_id para @%s na thread; pontuação ignorada.", username)
            continue
        balance = store.adjust_score(user_id, username, delta, reason, conversation_id)
        results.append((username, delta, balance))
    return results
