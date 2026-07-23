"""Cliente da X API v2 (tweepy): menções, threads e replies."""
from __future__ import annotations

import logging

import tweepy

from .config import Config

log = logging.getLogger(__name__)

TWEET_FIELDS = ["author_id", "conversation_id", "created_at", "in_reply_to_user_id",
                "referenced_tweets", "attachments", "entities"]
EXPANSIONS = ["author_id", "attachments.media_keys"]
USER_FIELDS = ["username", "name"]
MEDIA_FIELDS = ["url", "type"]


def _index_users(includes) -> dict:
    return {u.id: u for u in (includes or {}).get("users", [])}


def _index_media(includes) -> dict:
    return {m.media_key: m for m in (includes or {}).get("media", [])}


def _tweet_to_dict(tweet, users: dict, media: dict | None = None) -> dict:
    author = users.get(tweet.author_id)
    media_urls = []
    if media and tweet.attachments:
        for key in tweet.attachments.get("media_keys", []):
            m = media.get(key)
            if m is not None and m.type == "photo" and m.url:
                media_urls.append(m.url)
    return {
        "id": str(tweet.id),
        "conversation_id": str(tweet.conversation_id),
        "author_id": str(tweet.author_id),
        "author_username": author.username if author else None,
        "author_name": author.name if author else None,
        "text": tweet.text,
        "created_at": tweet.created_at.isoformat() if tweet.created_at else None,
        "media_urls": media_urls,
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

    def fetch_own_invites(self, since_id: str | None) -> list[dict]:
        """Tweets do próprio bot contendo 'convido' (convites do dono, sem limite)."""
        resp = self.client.search_recent_tweets(
            query=f'from:{self.cfg.bot_handle} "convido"',
            since_id=since_id,
            max_results=10,
            tweet_fields=TWEET_FIELDS,
            expansions=EXPANSIONS,
            user_fields=USER_FIELDS,
        )
        if not resp.data:
            return []
        users = _index_users(resp.includes)
        tweets = [_tweet_to_dict(t, users) for t in resp.data]
        tweets.sort(key=lambda m: int(m["id"]))
        return tweets

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
            media_fields=MEDIA_FIELDS,
        )
        if root.data:
            users = _index_users(root.includes)
            media = _index_media(root.includes)
            for t in root.data:
                tweets[str(t.id)] = _tweet_to_dict(t, users, media)

        # Replies da conversa
        paginator = tweepy.Paginator(
            self.client.search_recent_tweets,
            query=f"conversation_id:{conversation_id}",
            max_results=100,
            tweet_fields=TWEET_FIELDS,
            expansions=EXPANSIONS,
            user_fields=USER_FIELDS,
            media_fields=MEDIA_FIELDS,
        )
        for page in paginator:
            if not page.data:
                break
            users = _index_users(page.includes)
            media = _index_media(page.includes)
            for t in page.data:
                tweets[str(t.id)] = _tweet_to_dict(t, users, media)
            if len(tweets) >= max_tweets:
                break

        thread = sorted(tweets.values(), key=lambda t: int(t["id"]))
        return thread[:max_tweets]

    def get_user_location(self, username: str) -> str | None:
        """Campo `location` (texto livre) do perfil de um usuário, se houver."""
        try:
            resp = self.client.get_users(usernames=[username],
                                         user_fields=["location"])
            if resp.data:
                return resp.data[0].location
        except Exception:
            log.warning("Falha ao buscar location de @%s", username, exc_info=True)
        return None

    def post_poll(self, text: str, options: list[str], minutes: int,
                  in_reply_to_tweet_id: str) -> str | None:
        """Posta uma enquete como reply. Retorna o id do tweet ou None se proibido."""
        try:
            resp = self.client.create_tweet(
                text=text,
                poll_options=options,
                poll_duration_minutes=minutes,
                in_reply_to_tweet_id=in_reply_to_tweet_id,
            )
        except tweepy.errors.Forbidden as e:
            log.warning("Enquete proibida pelo X em %s: %s", in_reply_to_tweet_id, e)
            return None
        tweet_id = str(resp.data["id"]) if resp.data else None
        log.info("Enquete postada: %s", tweet_id)
        return tweet_id

    def fetch_poll_results(self, tweet_id: str) -> dict | None:
        """Resultado da enquete: {'closed': bool, 'votes': {label: n}} ou None."""
        resp = self.client.get_tweets(
            ids=[tweet_id],
            expansions=["attachments.poll_ids"],
            poll_fields=["options", "voting_status"],
        )
        polls = (resp.includes or {}).get("polls") or []
        if not polls:
            return None
        poll = polls[0]
        return {
            "closed": poll.voting_status == "closed",
            "votes": {opt["label"]: opt["votes"] for opt in poll.options},
        }

    def post_reply(self, text: str, in_reply_to_tweet_id: str,
                   fallback: str | None = None) -> str | None:
        """Posta um reply. Se o X recusar (403) e houver `fallback` (versão curta),
        tenta uma vez com ele. Retorna None se nada puder ser postado."""
        try:
            resp = self.client.create_tweet(
                text=text, in_reply_to_tweet_id=in_reply_to_tweet_id
            )
        except tweepy.errors.Forbidden as e:
            if fallback and fallback != text:
                log.warning("Reply longo recusado em %s; tentando versão curta: %s",
                            in_reply_to_tweet_id, e)
                return self.post_reply(fallback, in_reply_to_tweet_id)
            log.warning(
                "Reply proibido pelo X em %s (thread restrita ou tweet apagado): %s",
                in_reply_to_tweet_id, e,
            )
            return None
        tweet_id = str(resp.data["id"]) if resp.data else None
        log.info("Reply postado: %s", tweet_id)
        return tweet_id
