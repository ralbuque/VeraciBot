"""Reenfileira no outbox os vereditos cujo reply se perdeu (ex.: conta bloqueada).

Procura casos julgados SEM reply registrado nas últimas N horas (padrão 48) e
recria o texto do veredito (placar a partir do ledger + linha de composição).
O bot envia tudo no próximo ciclo, com espaçamento entre as escritas.

Uso (na raiz do repo, com o bot PARADO ou rodando, tanto faz):
    python scripts/requeue_replies.py [horas]
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.veracibot.config import load_config
from src.veracibot.reply import JUSTICE_LINE, composition_line, format_reply
from src.veracibot.store import Store


def main() -> None:
    hours = int(sys.argv[1]) if len(sys.argv) > 1 else 48
    cfg = load_config()
    store = Store(cfg.db_path)
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()

    rows = store.conn.execute(
        "SELECT conversation_id, mention_tweet_id, verdict_json FROM cases "
        "WHERE status = 'judged' AND (reply_tweet_id IS NULL OR reply_tweet_id = '') "
        "AND created_at >= ?",
        (cutoff,),
    ).fetchall()

    count = 0
    for conv_id, mention_id, verdict_json in rows:
        verdict = json.loads(verdict_json or "{}")
        if not verdict.get("julgavel"):
            continue
        scores = []
        for d in store.case_deltas(conv_id):
            balance = store.get_balance(d["user_id"], d["username"])
            scores.append((d["username"], d["total"], balance))
        comp = store.get_pending_composition(conv_id)
        if verdict.get("gravidade") == "grave":
            extra = f"{JUSTICE_LINE}\n👩‍⚖️ Advogados parceiros: {cfg.site_url}/advogados"
        elif comp:
            extra = composition_line(verdict.get("tipo_caso"),
                                     comp["loser_username"], comp["winner_username"])
        else:
            extra = None
        case_url = f"{cfg.site_url}/caso/{conv_id}"
        text = format_reply(verdict, scores, extra, cfg.max_reply_len, case_url)
        store.enqueue_post(text, mention_id)
        # marca o caso para não reenfileirar de novo numa segunda rodada do script
        store.conn.execute(
            "UPDATE cases SET reply_tweet_id = 'outbox' WHERE conversation_id = ?",
            (conv_id,),
        )
        store.conn.commit()
        count += 1
        print(f"enfileirado: caso {conv_id}")

    print(f"\n{count} veredito(s) recolocado(s) na fila. "
          f"O bot envia nos próximos ciclos (5 por ciclo, com espaçamento).")


if __name__ == "__main__":
    main()
