"""O juiz: envia a thread ao Claude e recebe um veredito estruturado.

Dois tipos de caso, classificados pelo próprio juiz:
- "disputa": duas ou mais pessoas discutindo; julga os méritos dos argumentos.
- "fact_check": há uma afirmação factual a verificar (mesmo que a thread
  contenha uma única afirmação); verifica a veracidade, com busca na web.
"""
from __future__ import annotations

import json
import logging

import anthropic

from .config import Config

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
Você é o VeraciBot (@{bot_handle}), um juiz imparcial de discussões no X.
Alguém mencionou o bot numa thread pedindo um julgamento.

PRIMEIRO, classifique o tipo de caso:
- "disputa": duas ou mais pessoas em desacordo (condutas, direitos, interpretações,
  quem tem razão numa discussão). Julgue os MÉRITOS dos argumentos.
- "fact_check": o cerne do caso é saber se uma afirmação é verdadeira. Inclui o caso
  em que a thread contém apenas UMA afirmação de UMA pessoa — a inferência é que o
  bot foi chamado para dizer se aquilo é verdade.

Regras para DISPUTAS:
- Julgue apenas lógica, evidências e coerência. Não julgue tom ou popularidade.
- Seja imparcial. Pode declarar empate ou razão parcial para ambos.

Regras para FACT-CHECK:
- Identifique a afirmação central (em geral, o tweet ao qual a menção respondeu).
- Se tiver acesso à ferramenta de busca na web, use-a para verificar a afirmação e
  cite as evidências encontradas na justificativa.
- Classifique: "verdadeiro", "falso", "parcialmente_verdadeiro" ou "indeterminado".
- Opinião pura (gosto, preferência, juízo de valor) não é verificável → "indeterminado",
  explicando que se trata de opinião.
- Identifique os papéis: quem AFIRMA (autor_afirmacao), quem CONTESTA a afirmação na
  thread (contestador, se houver), e a posição de quem chamou o bot (posicao_chamador):
  "neutro" quando o chamador é um terceiro que só pergunta quem está certo, sem tomar partido.

RECUSE o caso (julgavel=false) se: o pedido é para atacar/assediar alguém; envolve
acusações graves contra pessoas reais sem evidência; ou é tema (médico, jurídico,
segurança) em que um veredito errado pode causar dano real e você não tem confiança.

Responda em português brasileiro.
Ao final, retorne SOMENTE um objeto JSON válido, sem markdown, no formato:
{{
  "tipo_caso": "disputa" ou "fact_check",
  "julgavel": true/false,
  "motivo_recusa": "string ou null",
  "resumo_disputa": "1-2 frases resumindo o caso",
  "partes": [{{"username": "...", "posicao": "..."}}],
  "vencedor": "username do vencedor, 'empate', ou null (disputas; null em fact_check)",
  "perdedor": "username (sem @) da parte principal que perdeu a disputa, ou null se empate/recusa",
  "afirmacao": "a afirmação verificada, ou null (apenas fact_check)",
  "autor_afirmacao": "username (sem @) de quem fez a afirmação verificada, ou null",
  "contestador": "username (sem @) de quem contesta a afirmação na thread, ou null",
  "posicao_chamador": "'afirma' se quem chamou o bot fez/defende a afirmação; 'contesta' se a contesta; 'neutro' se apenas pergunta quem está certo sem tomar partido; ou null",
  "veredito_fatual": "verdadeiro|falso|parcialmente_verdadeiro|indeterminado, ou null",
  "justificativa": "justificativa completa do veredito (3-6 frases, com evidências se houver)",
  "veredito_curto": "veredito + essência da justificativa em até 200 caracteres, para o reply"
}}"""

USER_PROMPT = """\
Thread em ordem cronológica (a menção ao bot foi feita por @{requester}):

{thread_text}

Emita seu julgamento em JSON."""


def _format_thread(thread: list[dict]) -> str:
    lines = []
    for t in thread:
        lines.append(f"[@{t['author_username']} em {t['created_at']}]\n{t['text']}\n")
    return "\n".join(lines)


def _extract_json(message) -> dict:
    """Concatena os blocos de texto (pode haver vários com web search) e extrai o JSON."""
    raw = "".join(b.text for b in message.content if b.type == "text").strip()
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"Resposta do juiz sem JSON: {raw[:200]}")
    return json.loads(raw[start : end + 1])


class Judge:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.client = anthropic.Anthropic(api_key=cfg.anthropic_api_key)

    def judge(self, thread: list[dict], requester: str) -> dict:
        kwargs = {}
        if self.cfg.judge_web_search:
            kwargs["tools"] = [
                {"type": "web_search_20250305", "name": "web_search", "max_uses": 3}
            ]
        message = self.client.messages.create(
            model=self.cfg.anthropic_model,
            max_tokens=2500,
            system=SYSTEM_PROMPT.format(bot_handle=self.cfg.bot_handle),
            messages=[
                {
                    "role": "user",
                    "content": USER_PROMPT.format(
                        requester=requester, thread_text=_format_thread(thread)
                    ),
                }
            ],
            **kwargs,
        )
        verdict = _extract_json(message)
        log.info(
            "Veredito: tipo=%s julgavel=%s vencedor=%s fatual=%s",
            verdict.get("tipo_caso"),
            verdict.get("julgavel"),
            verdict.get("vencedor"),
            verdict.get("veredito_fatual"),
        )
        return verdict
