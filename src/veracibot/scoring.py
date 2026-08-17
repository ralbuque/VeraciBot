"""Sistema de pontuação do tribunal.

Regras (fact-check):
- Todo handle começa com 1000 pontos.
- Chamar o bot custa 1 ponto (exige saldo >= 1; estornado em erro interno).

FACT-CHECK — as partes são sempre o AUTOR da afirmação e QUEM CHAMOU o bot
(outros que desmentiram na thread não pontuam; a aposta é de quem aciona):
- Chamador contesta a afirmação (padrão): falsa → chamador +11 (líquido +10) e
  autor -11; verdadeira → chamador -10 (total -11) e autor +10.
- Self-check (autor confere a própria afirmação): verdadeira +11; falsa -10.
- Parcialmente verdadeiro / indeterminado / recusado: ninguém ganha nem perde;
  permanece só o custo do chamador.

DISPUTAS — as partes são quem argumentou (vencedor/perdedor indicados pelo juiz):
- Chamador vence: +11 (líquido +10); perdedor -11.
- Chamador perde: -10 (total -11); vencedor +10.
- Chamador NEUTRO (terceiro perguntando quem tem razão): só o custo;
  vencedor +10, perdedor -10.
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

    afs = verdict.get("afirmacoes") or [{
        "autor": verdict.get("autor_afirmacao"),
        "veredito": verdict.get("veredito_fatual"),
    }]
    req = requester_username.lower()

    # Cada afirmação pontua de forma independente. A aposta é sempre de quem
    # chamou o bot; quem desmentiu antes na thread não pontua.
    results: dict[str, list] = {}  # username_lower -> [username, delta_total, saldo]
    for af in afs:
        vf = (af.get("veredito") or "").lower()
        if vf not in ("verdadeiro", "falso"):
            continue  # indeterminado: neutro
        claim_true = vf == "verdadeiro"
        autor = _clean(af.get("autor"))
        autor_id = resolve_user_id(thread, autor) if autor else None
        self_check = bool(autor and autor.lower() == req) or (
            autor_id is not None and autor_id == requester_id
        )

        changes: list[tuple[str | None, str, int]] = []
        if self_check:
            changes.append((requester_id, requester_username,
                            +11 if claim_true else -10))
        else:
            caller_right = not claim_true
            changes.append((requester_id, requester_username,
                            +11 if caller_right else -10))
            if autor:
                changes.append((autor_id, autor, -11 if caller_right else +10))

        for username, delta, balance in _apply(
                store, changes, f"fact_check:{vf}", conversation_id):
            entry = results.setdefault(username.lower(), [username, 0, balance])
            entry[1] += delta
            entry[2] = balance

    return [tuple(v) for v in results.values()]


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
