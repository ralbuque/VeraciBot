"""Sistema de convites: quem pode chamar o tribunal.

- INVITE_ONLY=true no .env liga o modo convite.
- @veracibot (a própria conta, tweetando "Convido @handle") convida sem limite.
- Membros convidam até 5 pessoas: "@veracibot convido @handle".
- Não-convidados que chamarem o bot recebem o aviso UMA vez; depois, silêncio.
"""
from __future__ import annotations

import re

INVITES_PER_MEMBER = 5

INVITE_RE = re.compile(r"convido\s+@(\w{1,15})", re.IGNORECASE)

# Atenção: o exemplo usa "@…" de propósito — não pode casar com INVITE_RE, senão
# o próprio tweet de boas-vindas viraria um convite (o poller lê tweets do bot).
WELCOME = (
    "Seja bem-vindo(a) ao VeraciBot, {handles}! Você já pode chamar o bot em "
    "qualquer thread e convidar outras {n} pessoas — basta me mencionar com "
    "\"convido @…\". Saiba mais: veraci.bot"
)
INVITER_BALANCE = " @{inviter} ainda tem {left} convite(s)."
NOT_INVITED = (
    "Lamento, @{handle}, mas o VeraciBot só pode ser chamado por quem foi "
    "convidado. Procure alguém que participe do sistema e peça para te convidar. "
    "Saiba mais: veraci.bot"
)
NO_INVITES_LEFT = (
    "@{handle}, seus {n} convites já foram usados — não foi possível convidar {failed}."
)


def parse_invites(text: str, exclude: set[str]) -> list[str]:
    """Extrai handles convidados no texto, sem duplicatas e sem os excluídos."""
    seen, out = set(), []
    for h in INVITE_RE.findall(text):
        hl = h.lower()
        if hl not in seen and hl not in exclude:
            seen.add(hl)
            out.append(hl)
    return out
