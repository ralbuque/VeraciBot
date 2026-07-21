"""Loop principal do VeraciBot: poll → thread → julgamento → reply → persistência."""
import logging
import time

from .config import load_config
from .judge import Judge
from .reply import format_reply
from .scoring import CALL_COST, apply_scores
from .store import Store
from .x_client import XClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("veracibot")


def process_mention(mention: dict, x: XClient, judge: Judge, store: Store, cfg) -> None:
    conv_id = mention["conversation_id"]
    requester = mention["author_username"] or "desconhecido"
    requester_id = mention["author_id"]

    if store.case_exists(conv_id):
        log.info("Conversa %s já julgada; ignorando.", conv_id)
        return

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
        # Mostra o custo da chamada no placar quando o chamador não é parte apostadora.
        if all(u.lower() != requester.lower() for u, _, _ in scores):
            scores.append((requester, -CALL_COST, balance_after_cost))

        reply_id = None
        if cfg.post_replies:
            reply_text = format_reply(verdict, scores)
            reply_id = x.post_reply(reply_text, in_reply_to_tweet_id=mention["id"])

        status = "judged" if verdict.get("julgavel") else "declined"
        store.save_case(conv_id, mention["id"], requester, status,
                        verdict=verdict, reply_tweet_id=reply_id, thread=thread)
    except Exception:
        log.exception("Erro ao processar conversa %s", conv_id)
        store.adjust_score(requester_id, requester, +CALL_COST, "estorno_erro", conv_id)
        store.save_case(conv_id, mention["id"], requester, "error")


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
        except Exception:
            log.exception("Erro no ciclo de polling")
        time.sleep(cfg.poll_interval_seconds)


if __name__ == "__main__":
    run()
