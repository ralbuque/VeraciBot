"""Loop principal do VeraciBot: poll → thread → julgamento → reply → persistência."""
import logging
import re
import time

import tweepy
from datetime import datetime, timedelta, timezone

from .config import load_config
from .geo import extract_uf
from .invites import (INVITER_BALANCE, INVITES_PER_MEMBER, NO_INVITES_LEFT,
                      NOT_INVITED, NOT_INVITED_PROMO, WELCOME, parse_invites)
from .judge import Judge
from .reply import (JUSTICE_LINE, attach_tail, claim_reply, composition_line,
                    evidence_request, format_reply, multi_intro)
from .scoring import CALL_COST, apply_scores, resolve_user_id
from .store import Store
from .x_client import XClient

COMPOSITION_DAYS = 7
COMPOSITION_REFUND = 8
EVIDENCE_HOURS = 48


class CreditsExhausted(Exception):
    """Créditos da API Anthropic esgotados: pausar julgamentos sem perder menções."""
APPEAL_COST = 5
APPEAL_HOURS = 24

# --- Promoção "Em Busca da Verdade" ---
ENROLL_RE = re.compile(r"quero\s+participar", re.IGNORECASE)
PROMO_PRIZES = [3000, 1000, 500, 250, 250]  # μBTC: 1º ao 5º
PROMO_WELCOME = (
    "🔍 Inscrição confirmada, @{handle}! Em {start} os pontos dos participantes "
    "serão zerados em 1000; quem tiver mais pontos em {end} leva até 3.000 μBTC. "
    "Aponte fake news com @veracibot e boa caçada! Regras e prêmios: {site}"
)
PROMO_MISSING = (
    "🔍 @{handle}, para participar da promoção falta: {missing}. "
    "Depois é só repetir \"@veracibot quero participar\". Regras: {site}"
)

VOTE_RE = re.compile(r"voto\s+@(\w{1,15})", re.IGNORECASE)

APPEAL_TEXT = (
    "⚖️ RECURSO! @{loser} não concorda com a sentença e apela ao júri popular.\n"
    "🗳️ Membros do tribunal: votem em até {hours}h respondendo aqui "
    "\"voto @{winner}\" ou \"voto @{loser}\" (com menção a mim). Um voto por membro; "
    "só votos de membros convidados contam e as partes não votam. "
    "Quorum: {quorum} votos."
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("veracibot")


def process_mention(mention: dict, x: XClient, judge: Judge, store: Store, cfg) -> None:
    conv_id = mention["conversation_id"]
    requester = mention["author_username"] or "desconhecido"
    requester_id = mention["author_id"]

    # Inscrição na promoção ("@veracibot quero participar")?
    if cfg.promo_enabled and ENROLL_RE.search(mention["text"]):
        handle_enrollment(mention, x, store, cfg)
        return

    # Convite via menção de um membro ("@veracibot convido @fulano")?
    invited = parse_invites(mention["text"], exclude={cfg.bot_handle.lower(),
                                                      requester.lower()})
    if invited:
        handle_member_invites(mention, invited, x, store, cfg)
        return

    case = store.get_case(conv_id)
    if case:
        appeal = store.get_appeal(conv_id)
        if appeal and appeal["status"] == "aberta" and VOTE_RE.search(mention["text"]):
            handle_vote(mention, appeal, store, cfg)
        elif case["status"] == "aguardando_provas":
            handle_evidence(mention, x, judge, store, cfg, case)
        else:
            handle_followup(mention, x, judge, store, cfg)
        return

    # Modo convite: só membros abrem casos
    if cfg.invite_only and not store.is_member(requester):
        if not store.was_rejection_notified(requester):
            store.mark_rejection_notified(requester)
            log.info("@%s não é membro; avisando (uma vez).", requester)
            if cfg.post_replies:
                template = NOT_INVITED_PROMO if cfg.promo_enabled else NOT_INVITED
                x.post_reply(template.format(handle=requester),
                             in_reply_to_tweet_id=mention["id"])
        else:
            log.info("@%s não é membro; ignorando em silêncio.", requester)
        return
    if store.is_member(requester):
        store.set_member_user_id(requester, requester_id)

    # Saldo mínimo para abrir um caso
    balance = store.get_balance(requester_id, requester)
    if balance < CALL_COST:
        log.info("@%s sem saldo (%d); caso não aberto.", requester, balance)
        if cfg.post_replies:
            x.post_reply(
                f"⚖️ @{requester}, você está sem saldo de pontos para abrir um caso "
                f"(saldo: {balance}). Vença julgamentos para recuperar pontos.",
                in_reply_to_tweet_id=mention["id"],
            )
        return

    log.info("Novo caso: conversa %s (pedido de @%s, saldo %d)", conv_id, requester, balance)
    balance_after_cost = store.adjust_score(
        requester_id, requester, -CALL_COST, "custo_chamada", conv_id
    )
    try:
        thread = x.fetch_thread(conv_id, cfg.max_thread_tweets)
        # Nota: thread com 1 tweet é válida — pode ser fact-check de afirmação única.
        verdict = judge.judge(thread, requester)

        # Caso não-julgável (menção fora de contexto, sem disputa/afirmação):
        # silêncio total — sem reply, custo estornado; salva só para não reprocessar.
        if not verdict.get("julgavel"):
            store.adjust_score(requester_id, requester, +CALL_COST,
                               "estorno_arquivado", conv_id)
            store.save_case(conv_id, mention["id"], requester, "declined",
                            verdict=verdict, thread=thread)
            log.info("Caso %s arquivado em silêncio: %s", conv_id,
                     verdict.get("motivo_recusa"))
            return

        # Contradição factual decisiva: abre a fase de provas (sem pontuar ainda)
        if (verdict.get("fase") == "pedido_provas" and verdict.get("julgavel")
                and verdict.get("onus")):
            deadline = (datetime.now(timezone.utc)
                        + timedelta(hours=EVIDENCE_HOURS)).isoformat()
            verdict["provas_deadline"] = deadline
            reply_id = None
            if cfg.post_replies:
                reply_id = x.post_reply(
                    evidence_request(verdict, EVIDENCE_HOURS, cfg.max_reply_len),
                    in_reply_to_tweet_id=mention["id"],
                )
            store.save_case(conv_id, mention["id"], requester, "aguardando_provas",
                            verdict=verdict, reply_tweet_id=reply_id, thread=thread)
            log.info("Fase de provas aberta em %s: ônus de @%s até %s",
                     conv_id, verdict["onus"], deadline)
            return

        scores = apply_scores(
            store, verdict, requester_id, requester, thread, conv_id
        )
        extra = open_composition(verdict, scores, thread, requester_id, requester,
                                 conv_id, store)
        if verdict.get("julgavel") and verdict.get("gravidade") == "grave":
            extra = f"{JUSTICE_LINE}\n👩‍⚖️ Advogados parceiros: {cfg.site_url}/advogados"
        # Mostra o custo da chamada no placar quando o chamador não é parte apostadora.
        if all(u.lower() != requester.lower() for u, _, _ in scores):
            scores.append((requester, -CALL_COST, balance_after_cost))

        reply_id = None
        if cfg.post_replies:
            reply_id = post_verdict_replies(x, cfg, mention["id"], verdict,
                                            scores, extra, conv_id)

        status = "judged" if verdict.get("julgavel") else "declined"
        store.save_case(conv_id, mention["id"], requester, status,
                        verdict=verdict, reply_tweet_id=reply_id, thread=thread)
    except Exception as e:
        log.exception("Erro ao processar conversa %s", conv_id)
        store.adjust_score(requester_id, requester, +CALL_COST, "estorno_erro", conv_id)
        if "credit balance" in str(e).lower():
            raise CreditsExhausted() from e  # não salva o caso: rejulga na recarga
        store.save_case(conv_id, mention["id"], requester, "error")


def post_verdict_replies(x: XClient, cfg, in_reply_to: str, verdict: dict,
                         scores: list, extra: str | None, conv_id: str) -> str | None:
    """Publica o veredito. Fact-check com várias afirmações vira uma corrente:
    intro anunciando N afirmações + um reply por afirmação (placar no último)."""
    case_url = f"{cfg.site_url}/caso/{conv_id}"
    afs = verdict.get("afirmacoes") or []
    if verdict.get("tipo_caso") == "fact_check" and len(afs) > 1:
        first_id = x.post_reply(multi_intro(len(afs)),
                                in_reply_to_tweet_id=in_reply_to)
        prev = first_id or in_reply_to
        total = len(afs)
        for i, af in enumerate(afs, 1):
            text = claim_reply(i, total, af, cfg.max_reply_len)
            if i == total:
                text = attach_tail(text, scores, extra, cfg.max_reply_len, case_url)
            pid = x.post_reply(text, in_reply_to_tweet_id=prev)
            prev = pid or prev
        return first_id

    reply_text = format_reply(verdict, scores, extra, cfg.max_reply_len, case_url)
    fallback = (format_reply(verdict, scores, extra, case_url=case_url)
                if cfg.max_reply_len > 280 else None)
    return x.post_reply(reply_text, in_reply_to_tweet_id=in_reply_to,
                        fallback=fallback)


def open_composition(verdict, scores, thread, requester_id, requester, conv_id, store):
    """Abre uma composição se houver perdedor e vencedor claros. Retorna a linha do reply."""
    if not verdict.get("julgavel"):
        return None
    if verdict.get("gravidade") == "grave":
        return None  # main anexa a linha da justiça + advogados (precisa do cfg)

    losers = [u for u, d, _ in scores if d <= -10]
    winners = [u for u, d, _ in scores if d > 0]
    if not losers or not winners:
        return None
    loser, winner = losers[0], winners[0]

    def _uid(username):
        if username.lower() == requester.lower():
            return requester_id
        return resolve_user_id(thread, username)

    loser_id, winner_id = _uid(loser), _uid(winner)
    if not loser_id or not winner_id or loser_id == winner_id:
        return None

    deadline = (datetime.now(timezone.utc) + timedelta(days=COMPOSITION_DAYS)).isoformat()
    store.create_composition(conv_id, verdict.get("tipo_caso"), loser_id, loser,
                             winner_id, winner, deadline)
    log.info("Composição aberta: @%s deve reparar @%s até %s", loser, winner, deadline)
    return composition_line(verdict.get("tipo_caso"), loser, winner)


def handle_evidence(mention: dict, x: XClient, judge: Judge, store: Store,
                    cfg, case: dict) -> None:
    """Menção em caso aguardando provas: rejulga a thread atualizada (com imagens)."""
    conv_id = mention["conversation_id"]
    verdict0 = case["verdict"]
    expired = datetime.now(timezone.utc).isoformat() > (
        verdict0.get("provas_deadline") or "")
    requester = case["mention_author"] or "desconhecido"  # chamador original

    log.info("Fase de provas em %s: nova menção de @%s (prazo %s).",
             conv_id, mention["author_username"], "vencido" if expired else "em curso")
    try:
        thread = x.fetch_thread(conv_id, cfg.max_thread_tweets)
        verdict = judge.judge(thread, requester, evidence={
            "onus": verdict0.get("onus"),
            "fato": verdict0.get("fato_a_provar"),
            "expired": expired,
        })
        if verdict.get("fase") == "pedido_provas" and not expired:
            log.info("Juiz ainda aguarda provas em %s; sem novo reply.", conv_id)
            return

        requester_id = resolve_user_id(thread, requester) or mention["author_id"]

        # Veredito final não-julgável: mesmo tratamento silencioso.
        if not verdict.get("julgavel"):
            store.adjust_score(requester_id, requester, +CALL_COST,
                               "estorno_arquivado", conv_id)
            store.save_case(conv_id, case["mention_tweet_id"], requester, "declined",
                            verdict=verdict, thread=thread)
            log.info("Caso %s (fase de provas) arquivado em silêncio.", conv_id)
            return

        scores = apply_scores(store, verdict, requester_id, requester, thread, conv_id)
        extra = open_composition(verdict, scores, thread, requester_id, requester,
                                 conv_id, store)
        if verdict.get("julgavel") and verdict.get("gravidade") == "grave":
            extra = f"{JUSTICE_LINE}\n👩‍⚖️ Advogados parceiros: {cfg.site_url}/advogados"
        reply_id = None
        if cfg.post_replies:
            reply_id = post_verdict_replies(x, cfg, mention["id"], verdict,
                                            scores, extra, conv_id)
        status = "judged" if verdict.get("julgavel") else "declined"
        store.save_case(conv_id, case["mention_tweet_id"], requester, status,
                        verdict=verdict, reply_tweet_id=reply_id, thread=thread)
    except Exception:
        log.exception("Erro na fase de provas da conversa %s", conv_id)


def handle_followup(mention: dict, x: XClient, judge: Judge, store: Store, cfg) -> None:
    """Menção em caso julgado: confirmação de composição (vencedor) ou recurso (perdedor)."""
    conv_id = mention["conversation_id"]
    comp = store.get_pending_composition(conv_id)
    if comp and mention["author_id"] == comp["winner_id"]:
        handle_confirmation(mention, x, judge, store, cfg, comp)
        return

    # Recurso: só o perdedor, uma vez, custa APPEAL_COST pontos
    deltas = store.case_deltas(conv_id)
    losers = [d for d in deltas if d["total"] < 0]
    winners = [d for d in deltas if d["total"] > 0]
    if not losers or not winners:
        log.info("Conversa %s sem partes para recurso; ignorando.", conv_id)
        return
    loser = min(losers, key=lambda d: d["total"])
    winner = max(winners, key=lambda d: d["total"])
    if mention["author_id"] != loser["user_id"]:
        log.info("Menção em %s não é do perdedor nem confirmação; ignorando.", conv_id)
        return
    if store.get_appeal(conv_id):
        log.info("Conversa %s já teve recurso; ignorando.", conv_id)
        return
    if not judge.interpret_appeal(mention["text"], loser["username"]):
        log.info("Menção do perdedor em %s não é pedido de recurso.", conv_id)
        return

    balance = store.get_balance(loser["user_id"], loser["username"])
    if balance < APPEAL_COST:
        if cfg.post_replies:
            x.post_reply(
                f"⚖️ @{loser['username']}, recorrer custa {APPEAL_COST} pontos e seu "
                f"saldo é {balance}. Recurso indeferido.",
                in_reply_to_tweet_id=mention["id"],
            )
        return

    store.adjust_score(loser["user_id"], loser["username"], -APPEAL_COST,
                       "custo_recurso", conv_id)
    announce_id = None
    if cfg.post_replies:
        announce_id = x.post_reply(
            APPEAL_TEXT.format(loser=loser["username"], winner=winner["username"],
                               hours=APPEAL_HOURS, quorum=cfg.appeal_quorum),
            in_reply_to_tweet_id=mention["id"],
        )
    if not announce_id:
        store.adjust_score(loser["user_id"], loser["username"], +APPEAL_COST,
                           "estorno_recurso_falha", conv_id)
        log.warning("Anúncio do recurso falhou em %s; custo estornado.", conv_id)
        return
    ends_at = (datetime.now(timezone.utc)
               + timedelta(hours=APPEAL_HOURS)).isoformat()
    store.create_appeal(conv_id, loser["user_id"], loser["username"],
                        winner["username"], announce_id, ends_at)
    log.info("Recurso aberto em %s por @%s (votação até %s).",
             conv_id, loser["username"], ends_at)


def handle_vote(mention: dict, appeal: dict, store: Store, cfg) -> None:
    """Voto de membro num recurso aberto ('voto @fulano')."""
    conv_id = mention["conversation_id"]
    voter = (mention["author_username"] or "").lower()
    choice = VOTE_RE.search(mention["text"]).group(1).lower()
    parties = {appeal["appellant_username"].lower(),
               appeal["opponent_username"].lower()}

    if datetime.now(timezone.utc).isoformat() > appeal["ends_at"]:
        log.info("Voto de @%s em %s fora do prazo; ignorado.", voter, conv_id)
        return
    if voter in parties:
        log.info("Voto de @%s ignorado: é parte no caso %s.", voter, conv_id)
        return
    if cfg.invite_only and not store.is_member(voter):
        log.info("Voto de @%s ignorado: não é membro.", voter)
        return
    if choice not in parties:
        log.info("Voto de @%s em %s para @%s não é uma das partes; ignorado.",
                 voter, conv_id, choice)
        return
    store.record_vote(conv_id, mention["author_id"], voter, choice)
    log.info("Voto registrado em %s: @%s → @%s.", conv_id, voter, choice)


def handle_enrollment(mention: dict, x: XClient, store: Store, cfg) -> None:
    """Inscrição na promoção: exige selo azul (Premium) e seguir o bot."""
    uid = mention["author_id"]
    handle = mention["author_username"] or "?"
    if store.is_participant(uid):
        log.info("@%s já é participante da promoção; ignorando.", handle)
        return

    info = x.get_user_info(uid)
    missing = []
    if not info.get("verified"):
        missing.append("ter o selo azul (X Premium)")
    if not x.is_follower(uid):
        missing.append("seguir @" + cfg.bot_handle)
    if missing:
        log.info("Inscrição de @%s incompleta: %s", handle, missing)
        if cfg.post_replies:
            x.post_reply(
                PROMO_MISSING.format(handle=handle, missing=" e ".join(missing),
                                     site=cfg.site_url),
                in_reply_to_tweet_id=mention["id"],
            )
        return

    store.add_participant(uid, handle)
    if not store.is_member(handle):
        store.add_member(handle, invited_by="promo")
    # Se o reset já aconteceu, o recém-inscrito também parte de 1000.
    if store.get_state("promo_reset_done"):
        balance = store.get_balance(uid, handle)
        if balance != 1000:
            store.adjust_score(uid, handle, 1000 - balance, "promo_reset")
    log.info("Promoção: @%s inscrito.", handle)
    if cfg.post_replies:
        start = datetime.fromisoformat(cfg.promo_start).strftime("%d/%m")
        end = datetime.fromisoformat(cfg.promo_end)
        end_display = (end - timedelta(days=1)).strftime("%d/%m às 24h")
        x.post_reply(
            PROMO_WELCOME.format(handle=handle, start=start, end=end_display,
                                 site=cfg.site_url),
            in_reply_to_tweet_id=mention["id"],
        )


def flush_outbox(x: XClient, store: Store, cfg) -> None:
    """Reenvia escritas pendentes (ex.: perdidas com a conta bloqueada)."""
    if not cfg.post_replies:
        return
    for item in store.pending_outbox(limit=5):
        try:
            tweet_id = x.send_raw(item["text"], item["in_reply_to"])
            store.mark_outbox_sent(item["id"])
            log.info("Outbox: item %s enviado (tweet %s).", item["id"], tweet_id)
        except tweepy.errors.Forbidden as e:
            if "temporarily locked" in str(e).lower():
                store.bump_outbox_attempt(item["id"])
                log.warning("Outbox: conta ainda bloqueada; tentando no próximo ciclo.")
                break
            store.mark_outbox_failed(item["id"])
            log.warning("Outbox: item %s recusado definitivamente: %s", item["id"], e)
        except Exception:
            store.bump_outbox_attempt(item["id"])
            log.exception("Outbox: erro ao enviar item %s", item["id"])
            break


def promo_tick(x: XClient, store: Store, cfg) -> None:
    """Reset dos pontos no início e anúncio dos vencedores no fim da promoção."""
    if not cfg.promo_enabled:
        return
    now = datetime.now(timezone.utc)
    start = datetime.fromisoformat(cfg.promo_start)
    end = datetime.fromisoformat(cfg.promo_end)

    if now >= start and not store.get_state("promo_reset_done"):
        for p in store.participants():
            balance = store.get_balance(p["user_id"], p["username"])
            if balance != 1000:
                store.adjust_score(p["user_id"], p["username"], 1000 - balance,
                                   "promo_reset")
        store.set_state("promo_reset_done", "1")
        log.info("Promoção: pontos de %d participante(s) zerados em 1000.",
                 len(store.participants()))
        if cfg.post_replies:
            x.post_tweet(
                "🔍 Começou a caçada! Promoção Em Busca da Verdade: todos os "
                "participantes partem de 1000 pontos. Quem apontar mais fake news "
                f"até {(end - timedelta(days=1)).strftime('%d/%m')} às 24h leva até "
                f"3.000 μBTC. Regras: {cfg.site_url}"
            )

    if now >= end and not store.get_state("promo_winners_announced"):
        ranking = sorted(
            ((p, store.get_balance(p["user_id"], p["username"]))
             for p in store.participants()),
            key=lambda t: -t[1],
        )[:5]
        lines = ["🏆 Resultado da promoção Em Busca da Verdade:"]
        medals = ["🥇", "🥈", "🥉", "4º", "5º"]
        for i, (p, balance) in enumerate(ranking):
            lines.append(f"{medals[i]} @{p['username']} — {balance} pts — "
                         f"{PROMO_PRIZES[i]:,} μBTC".replace(",", "."))
        lines.append("Obrigado a todos que caçaram fake news com o tribunal! "
                     f"{cfg.site_url}")
        store.set_state("promo_winners_announced", "1")
        log.info("Promoção encerrada; vencedores: %s",
                 [p["username"] for p, _ in ranking])
        if cfg.post_replies:
            x.post_tweet("\n".join(lines))


def check_expired_compositions(x: XClient, store: Store, cfg) -> None:
    """Composições com prazo vencido: encerra e indica advogados parceiros."""
    now = datetime.now(timezone.utc).isoformat()
    for comp in store.expired_pending_compositions(now):
        if not comp:
            continue
        conv_id = comp["conversation_id"]
        store.resolve_composition(conv_id, "expirada")
        log.info("Composição expirada sem acordo em %s.", conv_id)
        case = store.get_case(conv_id)
        reply_to = (case or {}).get("reply_tweet_id") or (case or {}).get("mention_tweet_id")
        if not (cfg.post_replies and reply_to):
            continue
        url = f"{cfg.site_url}/advogados"
        uf = extract_uf(x.get_user_location(comp["winner_username"]))
        if uf:
            url += f"?uf={uf}"
        x.post_reply(
            f"⏳ O prazo de composição venceu sem acordo entre "
            f"@{comp['winner_username']} e @{comp['loser_username']}. "
            f"Para levar o caso adiante na justiça real, veja os advogados "
            f"parceiros do tribunal: {url}",
            in_reply_to_tweet_id=reply_to,
        )


def check_appeals(x: XClient, store: Store, cfg) -> None:
    """Apura votações de recurso encerradas e publica o acórdão."""
    now = datetime.now(timezone.utc).isoformat()
    for ap in store.open_appeals():
        if now < ap["ends_at"]:
            continue
        votes = store.count_votes(ap["conversation_id"])
        v_winner = votes.get(ap["opponent_username"].lower(), 0)
        v_loser = votes.get(ap["appellant_username"].lower(), 0)
        total = v_winner + v_loser
        reformed = total >= cfg.appeal_quorum and v_loser > v_winner

        conv_id = ap["conversation_id"]
        if reformed:
            deltas = {d["user_id"]: d for d in store.case_deltas(conv_id)}
            appellant = deltas.get(ap["appellant_id"])
            opponent = next((d for d in deltas.values()
                             if d["username"] == ap["opponent_username"]), None)
            new_balances = []
            if appellant and opponent:
                swing_a = opponent["total"] - appellant["total"]
                swing_o = appellant["total"] - opponent["total"]
                b_a = store.adjust_score(appellant["user_id"], appellant["username"],
                                         swing_a, "reforma_recurso", conv_id)
                b_o = store.adjust_score(opponent["user_id"], opponent["username"],
                                         swing_o, "reforma_recurso", conv_id)
                b_a = store.adjust_score(appellant["user_id"], appellant["username"],
                                         +APPEAL_COST, "estorno_recurso", conv_id)
                new_balances = [(appellant["username"], swing_a + APPEAL_COST, b_a),
                                (opponent["username"], swing_o, b_o)]
            comp = store.get_pending_composition(conv_id)
            if comp:
                store.resolve_composition(conv_id, "cancelada_recurso")
            store.resolve_appeal(conv_id, "reformada")
            text = (f"⚖️ ACÓRDÃO: por {v_loser}×{v_winner} ({total} votos), o povo "
                    f"REFORMOU a sentença. @{ap['appellant_username']} tem razão.")
            if new_balances:
                placar = " · ".join(f"@{u} {'+' if d > 0 else ''}{d} ({b} pts)"
                                    for u, d, b in new_balances)
                text += f"\n📊 {placar}"
        else:
            store.resolve_appeal(conv_id, "mantida")
            motivo = ("sem o quorum mínimo de votos, prevalece o juízo técnico"
                      if total < cfg.appeal_quorum else "o júri confirmou o veredito")
            text = (f"⚖️ ACÓRDÃO: por {v_winner}×{v_loser} ({total} votos), a "
                    f"sentença foi MANTIDA — {motivo}. Os {APPEAL_COST} pontos do "
                    f"recurso não retornam.")
        log.info("Recurso %s: %s (placar %d×%d).", conv_id,
                 "reformado" if reformed else "mantido", v_loser, v_winner)
        if cfg.post_replies:
            x.post_reply(text, in_reply_to_tweet_id=ap["poll_tweet_id"])


def handle_confirmation(mention: dict, x: XClient, judge: Judge, store: Store,
                        cfg, comp: dict) -> None:
    """O vencedor confirmando a composição."""
    conv_id = mention["conversation_id"]
    if datetime.now(timezone.utc).isoformat() > comp["deadline"]:
        store.resolve_composition(conv_id, "expirada")
        log.info("Composição de %s expirada.", conv_id)
        return
    if not judge.interpret_confirmation(mention["text"], comp):
        log.info("Menção do vencedor em %s não confirma cumprimento.", conv_id)
        return

    balance = store.adjust_score(comp["loser_id"], comp["loser_username"],
                                 +COMPOSITION_REFUND, "composicao_cumprida", conv_id)
    store.resolve_composition(conv_id, "cumprida")
    log.info("Composição cumprida em %s: @%s recupera %d pts (saldo %d).",
             conv_id, comp["loser_username"], COMPOSITION_REFUND, balance)
    if cfg.post_replies:
        x.post_reply(
            f"🤝 Composição cumprida, confirmada por @{comp['winner_username']}. "
            f"@{comp['loser_username']} recupera {COMPOSITION_REFUND} pontos "
            f"(saldo: {balance}). Caso encerrado.",
            in_reply_to_tweet_id=mention["id"],
        )


def handle_member_invites(mention, invited, x, store, cfg) -> None:
    """Um membro convidando gente via menção. Consome do saldo de 5 convites."""
    inviter = (mention["author_username"] or "").lower()
    member = store.get_member(inviter)
    if not member:
        if cfg.invite_only and not store.was_rejection_notified(inviter):
            store.mark_rejection_notified(inviter)
            if cfg.post_replies:
                template = NOT_INVITED_PROMO if cfg.promo_enabled else NOT_INVITED
                x.post_reply(template.format(handle=inviter),
                             in_reply_to_tweet_id=mention["id"])
        return

    accepted, failed = [], []
    for handle in invited:
        if store.is_member(handle):
            continue  # já é membro; não consome convite
        if store.get_member(inviter)["invites_left"] <= 0:
            failed.append("@" + handle)
            continue
        store.add_member(handle, invited_by=inviter, invites=INVITES_PER_MEMBER)
        store.use_invite(inviter)
        accepted.append("@" + handle)

    log.info("Convites de @%s: aceitos=%s esgotados=%s", inviter, accepted, failed)
    if cfg.post_replies:
        if accepted:
            left = store.get_member(inviter)["invites_left"]
            x.post_reply(
                WELCOME.format(handles=" ".join(accepted), n=INVITES_PER_MEMBER)
                + INVITER_BALANCE.format(inviter=inviter, left=left),
                in_reply_to_tweet_id=mention["id"],
            )
        elif failed:
            x.post_reply(
                NO_INVITES_LEFT.format(handle=inviter, n=INVITES_PER_MEMBER,
                                       failed=" ".join(failed)),
                in_reply_to_tweet_id=mention["id"],
            )


def poll_owner_invites(x: XClient, store: Store, cfg) -> None:
    """Tweets do próprio @veracibot com 'Convido @fulano': convites sem limite."""
    since = store.get_state("own_invites_since_id") or None
    try:
        tweets = x.fetch_own_invites(since)
    except tweepy.errors.BadRequest:
        # since_id com mais de 7 dias: fora da janela da busca recente → 400.
        log.warning("since_id dos convites do dono expirou (>7 dias); resetando.")
        store.set_state("own_invites_since_id", "")
        return
    for tweet in tweets:
        handles = parse_invites(tweet["text"], exclude={cfg.bot_handle.lower()})
        accepted = []
        for handle in handles:
            if not store.is_member(handle):
                store.add_member(handle, invited_by=cfg.bot_handle,
                                 invites=INVITES_PER_MEMBER)
                accepted.append("@" + handle)
        if accepted:
            log.info("Convites do dono: %s", accepted)
            if cfg.post_replies:
                x.post_reply(
                    WELCOME.format(handles=" ".join(accepted), n=INVITES_PER_MEMBER),
                    in_reply_to_tweet_id=tweet["id"],
                )
        store.set_state("own_invites_since_id", tweet["id"])


def run() -> None:
    cfg = load_config()
    store = Store(cfg.db_path)
    x = XClient(cfg)
    x.store = store  # habilita o outbox nas escritas
    judge = Judge(cfg)

    log.info("VeraciBot iniciado. Monitorando @%s a cada %ss. Replies: %s",
             cfg.bot_handle, cfg.poll_interval_seconds, cfg.post_replies)

    while True:
        try:
            since_id = store.get_since_id() or None
            try:
                mentions = x.fetch_mentions(since_id)
            except tweepy.errors.BadRequest:
                log.warning("since_id das menções expirou (>7 dias); resetando.")
                store.set_since_id("")
                mentions = []
            if mentions:
                log.info("%d menção(ões) nova(s).", len(mentions))
            for mention in mentions:
                try:
                    process_mention(mention, x, judge, store, cfg)
                except CreditsExhausted:
                    log.error("Créditos da Anthropic esgotados! Julgamentos pausados; "
                              "as menções pendentes serão reprocessadas após a recarga.")
                    break  # não avança o since_id: retenta no próximo ciclo
                store.set_since_id(mention["id"])
        except Exception:
            log.exception("Erro no processamento de menções")

        # Cada tarefa auxiliar falha sozinha, sem derrubar as demais.
        for task in (poll_owner_invites, check_appeals,
                     check_expired_compositions, promo_tick, flush_outbox):
            try:
                task(x, store, cfg)
            except Exception:
                log.exception("Erro em %s", task.__name__)

        time.sleep(cfg.poll_interval_seconds)


if __name__ == "__main__":
    run()
