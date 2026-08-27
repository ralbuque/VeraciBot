"""Cliente da X API v2 (tweepy): menções, threads e replies."""
from __future__ import annotations

import logging
import time

import tweepy

from .config import Config

log = logging.getLogger(__name__)

# Espaçamento mínimo entre escritas, para não parecer rajada de spam ao X.
WRITE_SPACING_SECONDS = 6


def _is_locked(exc: Exception) -> bool:
    return "temporarily locked" in str(exc).lower()

TWEET_FIELDS = ["author_id", "conversation_id", "created_at", "in_reply_to_user_id",
                "referenced_tweets", "attachments", "entities", "note_tweet"]
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
    quoted_id = None
    replied_to_id = None
    if tweet.referenced_tweets:
        for ref in tweet.referenced_tweets:
            if ref.type == "quoted":
                quoted_id = str(ref.id)
            elif ref.type == "replied_to":
                replied_to_id = str(ref.id)
    # Notas longas: o campo `text` traz só a prévia de 280 chars; o texto
    # completo vem em note_tweet (sem ele, o juiz lê argumentos decapitados).
    text = tweet.text
    note = getattr(tweet, "note_tweet", None)
    if note and note.get("text"):
        text = note["text"]
    return {
        "quoted_id": quoted_id,
        "replied_to_id": replied_to_id,
        "id": str(tweet.id),
        "conversation_id": str(tweet.conversation_id),
        "author_id": str(tweet.author_id),
        "author_username": author.username if author else None,
        "author_name": author.name if author else None,
        "text": text,
        "created_at": tweet.created_at.isoformat() if tweet.created_at else None,
        "media_urls": media_urls,
    }


class XClient:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.store = None       # anexado em main.run() para o outbox
        self._last_write = 0.0
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

    def fetch_thread(self, conversation_id: str, max_tweets: int,
                     priority: set[str] | None = None) -> list[dict]:
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

        # Segue quotes: tweets citados por alguém da thread (a afirmação contestada
        # costuma estar neles) — 1 nível de profundidade.
        quoted_ids = {t["quoted_id"] for t in tweets.values() if t.get("quoted_id")}
        quoted_ids -= set(tweets.keys())
        if quoted_ids:
            resp = self.client.get_tweets(
                ids=list(quoted_ids)[:20],
                tweet_fields=TWEET_FIELDS,
                expansions=EXPANSIONS,
                user_fields=USER_FIELDS,
                media_fields=MEDIA_FIELDS,
            )
            if resp.data:
                users = _index_users(resp.includes)
                media = _index_media(resp.includes)
                for t in resp.data:
                    d = _tweet_to_dict(t, users, media)
                    d["quoted_context"] = True
                    tweets[str(t.id)] = d

        thread = sorted(tweets.values(), key=lambda t: int(t["id"]))
        if len(thread) <= max_tweets:
            return thread
        if not priority:
            return thread[:max_tweets]
        # Corte com prioridade: tweets das partes (e raiz/citados) nunca são
        # descartados em favor de comentários de curiosos.
        pr = {p.lower().lstrip("@") for p in priority}
        keep = [t for t in thread
                if (t.get("author_username") or "").lower() in pr
                or t["id"] == conversation_id or t.get("quoted_context")]
        keep = keep[:max_tweets]
        if len(keep) < max_tweets:
            kept_ids = {t["id"] for t in keep}
            for t in thread:
                if t["id"] not in kept_ids:
                    keep.append(t)
                    if len(keep) >= max_tweets:
                        break
        return sorted(keep, key=lambda t: int(t["id"]))

    def me_id(self) -> str:
        """Id da própria conta do bot (cacheado)."""
        if not hasattr(self, "_me_id"):
            self._me_id = str(self.client.get_me(user_auth=True).data.id)
        return self._me_id

    def get_user_info(self, user_id: str) -> dict:
        """Dados públicos do usuário, incluindo selo de verificação."""
        try:
            resp = self.client.get_users(ids=[user_id],
                                         user_fields=["verified", "verified_type"])
            if resp.data:
                u = resp.data[0]
                return {"username": u.username, "verified": bool(u.verified),
                        "verified_type": getattr(u, "verified_type", None)}
        except Exception:
            log.warning("Falha ao buscar dados de %s", user_id, exc_info=True)
        return {"username": None, "verified": False, "verified_type": None}

    def is_follower(self, user_id: str, max_pages: int = 5) -> bool:
        """Verifica se user_id segue o bot (paginando a lista de seguidores)."""
        try:
            paginator = tweepy.Paginator(
                self.client.get_users_followers, id=self.me_id(), max_results=1000
            )
            pages = 0
            for page in paginator:
                if page.data and any(str(u.id) == user_id for u in page.data):
                    return True
                pages += 1
                if pages >= max_pages:
                    break
        except Exception:
            log.warning("Falha ao verificar seguidor %s", user_id, exc_info=True)
        return False

    def _throttle(self) -> None:
        wait = WRITE_SPACING_SECONDS - (time.time() - self._last_write)
        if wait > 0:
            time.sleep(wait)
        self._last_write = time.time()

    def send_raw(self, text: str, in_reply_to: str | None = None) -> str | None:
        """Envia com throttle; propaga exceções (uso interno e do outbox)."""
        self._throttle()
        kwargs = {"text": text}
        if in_reply_to:
            kwargs["in_reply_to_tweet_id"] = in_reply_to
        resp = self.client.create_tweet(**kwargs)
        return str(resp.data["id"]) if resp.data else None

    def post_tweet(self, text: str) -> str | None:
        """Tweet avulso (anúncios). Conta bloqueada/cota → vai para o outbox."""
        try:
            return self.send_raw(text)
        except tweepy.errors.TooManyRequests:
            if self.store:
                self.store.enqueue_post(text, None)
                log.warning("Cota da X API (429); tweet enfileirado no outbox.")
            return None
        except tweepy.errors.Forbidden as e:
            if _is_locked(e) and self.store:
                self.store.enqueue_post(text, None)
                log.warning("Conta bloqueada; tweet enfileirado no outbox.")
            else:
                log.warning("Tweet avulso proibido: %s", e)
            return None

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
        """Posta uma enquete como reply. Retorna o id do tweet ou None se falhar."""
        self._throttle()
        try:
            resp = self.client.create_tweet(
                text=text,
                poll_options=options,
                poll_duration_minutes=minutes,
                in_reply_to_tweet_id=in_reply_to_tweet_id,
            )
        except tweepy.errors.TooManyRequests:
            log.warning("Enquete não postada: cota da X API (429).")
            return None
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
        """Posta um reply. Conta bloqueada → outbox; 403 de tamanho → fallback;
        outros 403 (thread restrita/tweet apagado) → descarta com aviso."""
        try:
            tweet_id = self.send_raw(text, in_reply_to_tweet_id)
        except tweepy.errors.TooManyRequests:
            if self.store:
                self.store.enqueue_post(text, in_reply_to_tweet_id)
                log.warning("Cota da X API (429); reply enfileirado no outbox.")
            return None
        except tweepy.errors.Forbidden as e:
            if _is_locked(e):
                if self.store:
                    self.store.enqueue_post(text, in_reply_to_tweet_id)
                    log.warning("Conta bloqueada; reply enfileirado no outbox.")
                return None
            if fallback and fallback != text:
                log.warning("Reply longo recusado em %s; tentando versão curta: %s",
                            in_reply_to_tweet_id, e)
                return self.post_reply(fallback, in_reply_to_tweet_id)
            log.warning(
                "Reply proibido pelo X em %s (thread restrita ou tweet apagado): %s",
                in_reply_to_tweet_id, e,
            )
            return None
        log.info("Reply postado: %s", tweet_id)
        return tweet_id
