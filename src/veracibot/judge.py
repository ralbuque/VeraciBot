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

GRAVIDADE: classifique o caso como "leve" (desentendimentos cotidianos, danos materiais
pequenos, informação incorreta) ou "grave" (violência, agressão, ameaça, invasão,
crime, dano sério). Casos graves não recebem proposta de composição — o tribunal
recomenda procurar a justiça real.

CONTRADIÇÃO FACTUAL E PROVAS:
- Julgue primeiro pelo INCONTROVERSO: se dá para decidir pelos fatos que ambas as
  partes admitem (ou verificáveis via busca), decida direto (fase="veredito").
- Antes de pedir provas, verifique se a prova JÁ ESTÁ NA THREAD: imagens anexadas
  ([Imagem N]) e links compartilhados são provas já apresentadas — avalie-as e
  decida direto (fase="veredito"), sem pedir o que já consta dos autos.
- Só se as partes se contradizem sobre um fato DECISIVO e não há prova na thread
  nem como resolver por busca, retorne fase="pedido_provas": identifique quem tem o
  ÔNUS DA PROVA (quem alega o fato positivo — prova negativa não se exige) e o que
  deve provar.
- Padrão de prova: preponderância de evidências (verossimilhança, consistência,
  quem se esquiva), não certeza absoluta.
- Imagens anexadas na thread são numeradas no texto como [Imagem N]. Prints de
  e-mail/conversa são INDÍCIOS não autenticáveis — pese-os com essa ressalva na
  justificativa. Links públicos verificáveis pesam mais.
- A thread pode conter TWEETS CITADOS (quote): alguém citou um tweet de fora da
  conversa, em geral para contestá-lo. O tweet citado costuma conter a afirmação
  sob análise, e seu autor é parte no caso normalmente (autor_afirmacao).

Responda em português brasileiro.
Ao final, retorne SOMENTE um objeto JSON válido, sem markdown, no formato:
{{
  "tipo_caso": "disputa" ou "fact_check",
  "fase": "veredito" ou "pedido_provas",
  "contradicao": "resumo da contradição factual, ou null",
  "onus": "username (sem @) de quem deve provar, ou null",
  "fato_a_provar": "o fato que precisa de prova, ou null",
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
  "gravidade": "leve" ou "grave",
  "justificativa": "justificativa completa do veredito (3-6 frases, com evidências se houver)",
  "veredito_curto": "veredito + essência da justificativa em até 200 caracteres, para o reply"
}}"""

USER_PROMPT = """\
Thread em ordem cronológica (a menção ao bot foi feita por @{requester}):

{thread_text}

Emita seu julgamento em JSON."""

EVIDENCE_PROMPT = """\

FASE DE PROVAS EM CURSO: o tribunal já pediu que @{onus} provasse: "{fato}".
Prazo {prazo_status}. A thread acima é a versão atualizada, incluindo o que foi
apresentado (textos, links e imagens anexadas).
Emita agora o VEREDITO FINAL (fase="veredito"): avalie as provas apresentadas com
o padrão de preponderância. Se a prova NÃO foi apresentada e o prazo venceu, a
alegação é improcedente — quem tinha o ônus perde. Não peça provas novamente."""

MAX_IMAGES = 4
MAX_IMAGE_BYTES = 4_500_000


def _format_thread(thread: list[dict]) -> str:
    by_id = {t["id"]: t for t in thread if t.get("id")}
    lines = []
    n_img = 0
    for t in thread:
        header = f"[@{t['author_username']} em {t['created_at']}]"
        if t.get("quoted_context"):
            header += " [TWEET CITADO — fora da thread]"
        qid = t.get("quoted_id")
        if qid and qid in by_id:
            header += f" (cita o tweet de @{by_id[qid]['author_username']} acima)"
        for _ in t.get("media_urls") or []:
            n_img += 1
            header += f" [Imagem {n_img}]"
        lines.append(f"{header}\n{t['text']}\n")
    return "\n".join(lines)


def _download_images(thread: list[dict]) -> list[dict]:
    """Baixa até MAX_IMAGES fotos da thread e retorna blocos de imagem da API."""
    import base64

    import requests

    blocks = []
    for t in thread:
        for url in t.get("media_urls") or []:
            if len(blocks) >= MAX_IMAGES:
                return blocks
            try:
                r = requests.get(url, timeout=15)
                r.raise_for_status()
                if len(r.content) > MAX_IMAGE_BYTES:
                    continue
                media_type = r.headers.get("content-type", "image/jpeg").split(";")[0]
                if not media_type.startswith("image/"):
                    continue
                blocks.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": base64.b64encode(r.content).decode(),
                    },
                })
            except Exception:
                log.warning("Falha ao baixar imagem %s", url, exc_info=True)
    return blocks


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

    def judge(self, thread: list[dict], requester: str,
              evidence: dict | None = None) -> dict:
        """Julga a thread. `evidence` = {'onus','fato','expired'} na fase de provas."""
        kwargs = {}
        if self.cfg.judge_web_search:
            kwargs["tools"] = [
                {"type": "web_search_20250305", "name": "web_search", "max_uses": 3}
            ]
        text = USER_PROMPT.format(requester=requester, thread_text=_format_thread(thread))
        if evidence:
            text += EVIDENCE_PROMPT.format(
                onus=evidence["onus"],
                fato=evidence["fato"],
                prazo_status="VENCIDO" if evidence["expired"] else "ainda em curso",
            )
        content: list = _download_images(thread)
        content.append({"type": "text", "text": text})
        message = self.client.messages.create(
            model=self.cfg.anthropic_model,
            max_tokens=2500,
            system=SYSTEM_PROMPT.format(bot_handle=self.cfg.bot_handle),
            messages=[{"role": "user", "content": content}],
            **kwargs,
        )
        verdict = _extract_json(message)
        log.info(
            "Veredito: tipo=%s julgavel=%s vencedor=%s fatual=%s gravidade=%s",
            verdict.get("tipo_caso"),
            verdict.get("julgavel"),
            verdict.get("vencedor"),
            verdict.get("veredito_fatual"),
            verdict.get("gravidade"),
        )
        return verdict

    def interpret_appeal(self, mention_text: str, loser: str) -> bool:
        """A parte perdedora respondeu na thread: isso é um pedido de recurso?"""
        message = self.client.messages.create(
            model=self.cfg.anthropic_model,
            max_tokens=100,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"@{loser} perdeu um julgamento do tribunal e respondeu na "
                        f"thread:\n\n\"{mention_text}\"\n\n"
                        "Isso expressa DISCORDÂNCIA da sentença / pedido de recurso "
                        "ou revisão? (Desculpas, aceitação ou outro assunto = false.) "
                        'Responda SOMENTE o JSON {"recurso": true} ou {"recurso": false}.'
                    ),
                }
            ],
        )
        try:
            return bool(_extract_json(message).get("recurso"))
        except (ValueError, json.JSONDecodeError):
            return False

    def interpret_confirmation(self, mention_text: str, comp: dict) -> bool:
        """O vencedor respondeu numa composição pendente: isso confirma o cumprimento?"""
        message = self.client.messages.create(
            model=self.cfg.anthropic_model,
            max_tokens=100,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"O tribunal aguarda @{comp['winner_username']} confirmar que "
                        f"@{comp['loser_username']} cumpriu a reparação combinada "
                        f"(desculpas/retratação). @{comp['winner_username']} respondeu:\n\n"
                        f"\"{mention_text}\"\n\n"
                        "Isso confirma o cumprimento? Responda SOMENTE o JSON "
                        '{"confirmacao": true} ou {"confirmacao": false}.'
                    ),
                }
            ],
        )
        try:
            return bool(_extract_json(message).get("confirmacao"))
        except (ValueError, json.JSONDecodeError):
            return False
