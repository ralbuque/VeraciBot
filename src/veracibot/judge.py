"""O juiz: envia a thread ao Claude e recebe um veredito estruturado.

Dois tipos de caso, classificados pelo próprio juiz:
- "disputa": duas ou mais pessoas discutindo; julga os méritos dos argumentos.
- "fact_check": há uma afirmação factual a verificar (mesmo que a thread
  contenha uma única afirmação); verifica a veracidade, com busca na web.
"""
from __future__ import annotations

import json
import logging
import re

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
- DECOMPONHA o caso em AFIRMAÇÕES FACTUAIS INDEPENDENTES (máximo 4), cada uma
  atômica e julgável por si. "Cortou o salário mínimo e sancionou lei X" são DUAS
  afirmações, com dois vereditos separados.
- Se tiver acesso à ferramenta de busca na web, use-a para verificar cada afirmação
  e cite as evidências na justificativa correspondente.
- Cada afirmação recebe: "verdadeiro", "falso" ou "indeterminado". NÃO existe
  "parcialmente verdadeiro": julgue a afirmação COMO ENUNCIADA (leitura literal) —
  exagero ou distorção relevante a torna FALSA ("cortou" quando houve estagnação é
  falso). "Indeterminado" é só para o que não se pode verificar.
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
NUNCA use tags de citação como <cite> no texto — mencione as fontes em linguagem
natural na justificativa (ex.: "segundo o Metrópoles, ...").
Ao final, retorne SOMENTE um objeto JSON válido, sem markdown, no formato:
{{
  "tipo_caso": "disputa" ou "fact_check",
  "fase": "veredito" ou "pedido_provas",
  "contradicao": "resumo da contradição factual, ou null",
  "onus": "username (sem @) de quem deve provar, ou null",
  "fato_a_provar": "o fato que precisa de prova, ou null",
  "julgavel": true/false,
  "motivo_recusa": "string ou null",
  "recusa_silenciosa": "true se a menção NEM ERA um pedido de julgamento (conversa casual, sem afirmação nem disputa) — o bot não responde nada; false se houve pedido genuíno mas o tribunal recusa — o bot responde explicando o motivo_recusa; null se julgavel=true",
  "resumo_disputa": "1-2 frases resumindo o caso",
  "partes": [{{"username": "...", "posicao": "..."}}],
  "vencedor": "username do vencedor, 'empate', ou null (disputas; null em fact_check)",
  "perdedor": "username (sem @) da parte principal que perdeu a disputa, ou null se empate/recusa",
  "afirmacao": "a afirmação principal verificada, ou null (apenas fact_check)",
  "autor_afirmacao": "username (sem @) de quem fez a afirmação principal, ou null",
  "afirmacoes": [{{"texto": "afirmação atômica", "autor": "username sem @", "veredito": "verdadeiro|falso|indeterminado", "justificativa": "2-4 frases com evidências"}}],
  "contestador": "username (sem @) de quem contesta a afirmação na thread, ou null",
  "posicao_chamador": "'afirma' se quem chamou o bot fez/defende a afirmação; 'contesta' se a contesta; 'neutro' se apenas pergunta quem está certo sem tomar partido; ou null",
  "veredito_fatual": "verdadeiro|falso|indeterminado quando há UMA afirmação; null se houver várias",
  "gravidade": "leve" ou "grave",
  "justificativa": "resumo geral do julgamento (3-6 frases)",
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


# Tags de citação da busca na web (ex.: <cite index="1-1">...</cite>), nas formas
# crua e com aspas escapadas dentro de strings JSON.
_CITE_RE = re.compile(r"</?cite[^>]*?>|<cite\s+index=\\\"[^>]*?\\\">|</cite>")


def _strip_cites(obj):
    if isinstance(obj, str):
        return _CITE_RE.sub("", obj)
    if isinstance(obj, list):
        return [_strip_cites(v) for v in obj]
    if isinstance(obj, dict):
        return {k: _strip_cites(v) for k, v in obj.items()}
    return obj


def _extract_json(message) -> dict:
    """Concatena os blocos de texto (pode haver vários com web search) e extrai o JSON."""
    raw = "".join(b.text for b in message.content if b.type == "text").strip()
    raw = _CITE_RE.sub("", raw)  # antes do parse: as aspas das tags quebram o JSON
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"Resposta do juiz sem JSON: {raw[:200]}")
    return _strip_cites(json.loads(raw[start : end + 1]))


MAX_CLAIMS = 4


def _normalize_fact(verdict: dict) -> dict:
    """Garante `afirmacoes` normalizada (máx 4, vereditos binários+indeterminado)
    e mantém os campos legados coerentes quando há uma única afirmação."""
    if verdict.get("tipo_caso") != "fact_check":
        return verdict
    afs = verdict.get("afirmacoes") or []
    if not afs and verdict.get("afirmacao"):
        afs = [{
            "texto": verdict.get("afirmacao"),
            "autor": verdict.get("autor_afirmacao"),
            "veredito": verdict.get("veredito_fatual"),
            "justificativa": verdict.get("justificativa"),
        }]
    norm = []
    for af in afs[:MAX_CLAIMS]:
        v = (af.get("veredito") or "indeterminado").lower()
        if v not in ("verdadeiro", "falso"):
            v = "indeterminado"  # inclui o extinto 'parcialmente_verdadeiro'
        norm.append({
            "texto": af.get("texto") or "",
            "autor": (af.get("autor") or verdict.get("autor_afirmacao") or "").lstrip("@"),
            "veredito": v,
            "justificativa": af.get("justificativa") or "",
        })
    verdict["afirmacoes"] = norm
    if len(norm) == 1:
        verdict["afirmacao"] = norm[0]["texto"] or verdict.get("afirmacao")
        verdict["autor_afirmacao"] = norm[0]["autor"] or verdict.get("autor_afirmacao")
        verdict["veredito_fatual"] = norm[0]["veredito"]
    elif norm:
        verdict["veredito_fatual"] = None
    return verdict


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
        verdict = _normalize_fact(_extract_json(message))
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
