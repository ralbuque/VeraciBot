"""Configuração via variáveis de ambiente (.env)."""
import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Variável de ambiente obrigatória ausente: {name}")
    return value


@dataclass(frozen=True)
class Config:
    # X API
    x_bearer_token: str
    x_api_key: str
    x_api_secret: str
    x_access_token: str
    x_access_token_secret: str
    # Anthropic
    anthropic_api_key: str
    anthropic_model: str
    # Bot
    bot_handle: str
    poll_interval_seconds: int
    db_path: str
    post_replies: bool
    max_thread_tweets: int
    judge_web_search: bool
    invite_only: bool


def load_config() -> Config:
    return Config(
        x_bearer_token=_require("X_BEARER_TOKEN"),
        x_api_key=_require("X_API_KEY"),
        x_api_secret=_require("X_API_SECRET"),
        x_access_token=_require("X_ACCESS_TOKEN"),
        x_access_token_secret=_require("X_ACCESS_TOKEN_SECRET"),
        anthropic_api_key=_require("ANTHROPIC_API_KEY"),
        anthropic_model=os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-5"),
        bot_handle=os.environ.get("BOT_HANDLE", "tribunalbot").lstrip("@"),
        poll_interval_seconds=int(os.environ.get("POLL_INTERVAL_SECONDS", "120")),
        db_path=os.environ.get("DB_PATH", "veracibot.db"),
        post_replies=os.environ.get("POST_REPLIES", "true").lower() == "true",
        max_thread_tweets=int(os.environ.get("MAX_THREAD_TWEETS", "50")),
        judge_web_search=os.environ.get("JUDGE_WEB_SEARCH", "true").lower() == "true",
        invite_only=os.environ.get("INVITE_ONLY", "false").lower() == "true",
    )
