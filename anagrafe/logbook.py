"""Log delle modifiche al registro su un canale Telegram."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from telegram.error import TelegramError
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


def now_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def fmt_utente(user) -> str:
    """Rappresentazione leggibile di un utente Telegram per i log."""
    if user is None:
        return "sconosciuto"
    if getattr(user, "username", None):
        return f"@{user.username} ({user.id})"
    return f"{user.full_name} ({user.id})"


def fmt_username(username: str | None) -> str:
    return f"@{username}" if username else "(nessuno username)"


async def send_log(context: ContextTypes.DEFAULT_TYPE, testo: str) -> None:
    """Invia un messaggio di log sul canale configurato, se ce n'è uno.

    Non fa mai fallire il comando chiamante: se il canale non e' configurato,
    il bot non ne e' amministratore o il canale non e' raggiungibile, l'errore
    viene solo registrato localmente.
    """
    settings = context.bot_data.get("settings")
    canale = getattr(settings, "log_channel_id", None)
    if not canale:
        return
    try:
        await context.bot.send_message(
            chat_id=canale,
            text=f"{testo}\nQuando: {now_str()}",
            parse_mode="Markdown",
            disable_web_page_preview=True,
        )
    except TelegramError as exc:
        logger.warning("Impossibile inviare il log sul canale %s: %s", canale, exc)
