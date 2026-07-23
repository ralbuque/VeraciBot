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

WELCOME = (
    "Seja bem-vindo(a) ao VeraciBot, {handles}! Você já pode chamar o bot em "
    "qualquer thread e convidar outras {n} pessoas (\"@veracibot convido @fulano\"). "
    "Saiba mais: veraci.bot"
)
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
