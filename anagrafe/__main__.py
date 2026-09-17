"""Punto di ingresso: python -m anagrafe"""

from __future__ import annotations

import logging
import sys

from telegram import BotCommand
from telegram.ext import Application

from .commands import comandi_menu_telegram
from .config import ConfigurazioneMancante, load_settings
from .db import init_db
from .handlers import registra_handlers
from .roles import RoleRegistry

logger = logging.getLogger("anagrafe")


def configura_logging() -> None:
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO,
    )
    # httpx logga ogni chiamata all'API di Telegram: troppo rumore a INFO.
    logging.getLogger("httpx").setLevel(logging.WARNING)


async def post_init(application: Application) -> None:
    """Imposta il menu nativo di Telegram con i soli comandi pubblici."""
    await application.bot.set_my_commands(
        [BotCommand(nome, descrizione) for nome, descrizione in comandi_menu_telegram()]
    )


def build_application(settings) -> Application:
    application = (
        Application.builder().token(settings.token).post_init(post_init).build()
    )
    application.bot_data["settings"] = settings
    application.bot_data["roles"] = RoleRegistry(
        root_admin_id=settings.root_admin_id, admins_path=settings.admins_path
    )
    registra_handlers(application)
    return application


def main() -> int:
    configura_logging()

    try:
        settings = load_settings()
    except ConfigurazioneMancante as exc:
        logger.error("%s", exc)
        return 1

    init_db(settings.db_path)
    logger.info("Registro: %s", settings.db_path)
    logger.info("Amministratori: %s", settings.admins_path)
    if settings.log_channel_id:
        logger.info("Canale di log: %s", settings.log_channel_id)

    application = build_application(settings)
    logger.info("Bot avviato, in ascolto...")
    application.run_polling()
    return 0


if __name__ == "__main__":
    sys.exit(main())
