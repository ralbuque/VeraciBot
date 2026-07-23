"""Cliente da X API v2 (tweepy): menções, threads e replies."""
from __future__ import annotations

import logging

import tweepy

from .config import Config

log = logging.getLogger(__name__)

TWEET_FIELDS = ["author_id", "conversation_id", "created_at", "in_reply_to_user_id", "referenced_tweets"]
EXPANSIONS = ["author_id"]
USER_FIELDS = ["username", "name"]


def _index_users(includes) -> dict:
    return {u.id: u for u in (includes or {}).get("users", [])}


def _tweet_to_dict(tweet, users: dict) -> dict:
    author = users.get(tweet.author_id)
    return {
        "id": str(tweet.id),
        "conversation_id": str(tweet.conversation_id),
        "author_id": str(tweet.author_id),
        "author_username": author.username if author else None,
        "author_name": author.name if author else None,
        "text": tweet.text,
        "created_at": tweet.created_at.isoformat() if tweet.created_at else None,
    }


class XClient:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        # Leitura (app-only) e escrita (user context) no mesmo client.
        self.client = tweepy.Client(
            bearer_token=cfg.x_bearer_token,
            consumer_key=cfg.x_api_key,
            consumer_secret=cfg.x_api_secret,
            access_token=cfg.x_access_token,
            access_token_secret=cfg.x_access_token_secret,
            wait_on_rate_limit=True,
        )

    def fetch_mentions(self, since_id: str | None) -> list[dict]:
        """Menções novas ao bot (exclui retweets e o próprio bot)."""
        query = f"@{self.cfg.bot_handle} -is:retweet -from:{self.cfg.bot_handle}"
        resp = self.client.search_recent_tweets(
            query=query,
            since_id=since_id,
            max_results=25,
            tweet_fields=TWEET_FIELDS,
            expansions=EXPANSIONS,
            user_fields=USER_FIELDS,
        )
        if not resp.data:
            return []
        users = _index_users(resp.includes)
        mentions = [_tweet_to_dict(t, users) for t in resp.data]
        mentions.sort(key=lambda m: int(m["id"]))  # mais antigas primeiro
        return mentions

    def fetch_thread(self, conversation_id: str, max_tweets: int) -> list[dict]:
        """Reconstrói a thread: tweet raiz + replies da conversa, em ordem cronológica.

        Limitação do plano Basic: a busca recente só cobre os últimos 7 dias.
        """
        tweets: dict[str, dict] = {}

        # Tweet raiz (id == conversation_id)
        root = self.client.get_tweets(
            ids=[conversation_id],
            tweet_fields=TWEET_FIELDS,
            expansions=EXPANSIONS,
            user_fields=USER_FIELDS,
        )
        if root.data:
            users = _index_users(root.includes)
            for t in root.data:
                tweets[str(t.id)] = _tweet_to_dict(t, users)

        # Replies da conversa
        paginator = tweepy.Paginator(
            self.client.search_recent_tweets,
            query=f"conversation_id:{conversation_id}",
            max_results=100,
            tweet_fields=TWEET_FIELDS,
            expansions=EXPANSIONS,
            user_fields=USER_FIELDS,
        )
        for page in paginator:
            if not page.data:
                break
            users = _index_users(page.includes)
            for t in page.data:
                tweets[str(t.id)] = _tweet_to_dict(t, users)
            if len(tweets) >= max_tweets:
                break

        thread = sorted(tweets.values(), key=lambda t: int(t["id"]))
        return thread[:max_tweets]

    def post_reply(self, text: str, in_reply_to_tweet_id: str) -> str | None:
        """Posta um reply. Retorna None (sem levantar exceção) se o X proibir a
        resposta — ex.: thread com replies restritos ou tweet apagado."""
        try:
            resp = self.client.create_tweet(
                text=text, in_reply_to_tweet_id=in_reply_to_tweet_id
            )
        except tweepy.errors.Forbidden as e:
            log.warning(
                "Reply proibido pelo X em %s (thread restrita ou tweet apagado): %s",
                in_reply_to_tweet_id, e,
            )
            return None
        tweet_id = str(resp.data["id"]) if resp.data else None
        log.info("Reply postado: %s", tweet_id)
        return tweet_id
