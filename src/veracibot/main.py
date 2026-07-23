"""Loop principal do VeraciBot: poll → thread → julgamento → reply → persistência."""
import logging
import time
from datetime import datetime, timedelta, timezone

from .config import load_config
from .invites import (INVITES_PER_MEMBER, NO_INVITES_LEFT, NOT_INVITED, WELCOME,
                      parse_invites)
from .judge import Judge
from .reply import JUSTICE_LINE, composition_line, format_reply
from .scoring import CALL_COST, apply_scores, resolve_user_id
from .store import Store
from .x_client import XClient

COMPOSITION_DAYS = 7
COMPOSITION_REFUND = 8

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("veracibot")


def process_mention(mention: dict, x: XClient, judge: Judge, store: Store, cfg) -> None:
    conv_id = mention["conversation_id"]
    requester = mention["author_username"] or "desconhecido"
    requester_id = mention["author_id"]

    # Convite via menção de um membro ("@veracibot convido @fulano")?
    invited = parse_invites(mention["text"], exclude={cfg.bot_handle.lower(),
                                                      requester.lower()})
    if invited:
        handle_member_invites(mention, invited, x, store, cfg)
        return

    if store.case_exists(conv_id):
        handle_confirmation(mention, x, judge, store, cfg)
        return

    # Modo convite: só membros abrem casos
    if cfg.invite_only and not store.is_member(requester):
        if not store.was_rejection_notified(requester):
            store.mark_rejection_notified(requester)
            log.info("@%s não é membro; avisando (uma vez).", requester)
            if cfg.post_replies:
                x.post_reply(NOT_INVITED.format(handle=requester),
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

        scores = apply_scores(
            store, verdict, requester_id, requester, thread, conv_id
        )
        extra = open_composition(verdict, scores, thread, requester_id, requester,
                                 conv_id, store)
        # Mostra o custo da chamada no placar quando o chamador não é parte apostadora.
        if all(u.lower() != requester.lower() for u, _, _ in scores):
            scores.append((requester, -CALL_COST, balance_after_cost))

        reply_id = None
        if cfg.post_replies:
            reply_text = format_reply(verdict, scores, extra)
            reply_id = x.post_reply(reply_text, in_reply_to_tweet_id=mention["id"])

        status = "judged" if verdict.get("julgavel") else "declined"
        store.save_case(conv_id, mention["id"], requester, status,
                        verdict=verdict, reply_tweet_id=reply_id, thread=thread)
    except Exception:
        log.exception("Erro ao processar conversa %s", conv_id)
        store.adjust_score(requester_id, requester, +CALL_COST, "estorno_erro", conv_id)
        store.save_case(conv_id, mention["id"], requester, "error")


def open_composition(verdict, scores, thread, requester_id, requester, conv_id, store):
    """Abre uma composição se houver perdedor e vencedor claros. Retorna a linha do reply."""
    if not verdict.get("julgavel"):
        return None
    if verdict.get("gravidade") == "grave":
        return JUSTICE_LINE

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


def handle_confirmation(mention: dict, x: XClient, judge: Judge, store: Store, cfg) -> None:
    """Menção em caso já julgado: pode ser o vencedor confirmando a composição."""
    conv_id = mention["conversation_id"]
    comp = store.get_pending_composition(conv_id)
    if not comp:
        log.info("Conversa %s já julgada e sem composição pendente; ignorando.", conv_id)
        return
    if mention["author_id"] != comp["winner_id"]:
        log.info("Menção em %s não é do vencedor (@%s); ignorando.",
                 conv_id, comp["winner_username"])
        return
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
                x.post_reply(NOT_INVITED.format(handle=inviter),
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
            x.post_reply(
                WELCOME.format(handles=" ".join(accepted), n=INVITES_PER_MEMBER),
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
    since = store.get_state("own_invites_since_id")
    for tweet in x.fetch_own_invites(since):
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
    judge = Judge(cfg)

    log.info("VeraciBot iniciado. Monitorando @%s a cada %ss. Replies: %s",
             cfg.bot_handle, cfg.poll_interval_seconds, cfg.post_replies)

    while True:
        try:
            since_id = store.get_since_id()
            mentions = x.fetch_mentions(since_id)
            if mentions:
                log.info("%d menção(ões) nova(s).", len(mentions))
            for mention in mentions:
                process_mention(mention, x, judge, store, cfg)
                store.set_since_id(mention["id"])
            poll_owner_invites(x, store, cfg)
        except Exception:
            log.exception("Erro no ciclo de polling")
        time.sleep(cfg.poll_interval_seconds)


if __name__ == "__main__":
    run()
