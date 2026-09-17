"""Handler di contorno: aggiornamento automatico degli username e catch-all."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from .. import repository
from ..commands import render_help
from ..logbook import fmt_username, send_log
from .common import db, rispondi, ruolo_utente

logger = logging.getLogger(__name__)


async def on_group_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Quando un cittadino scrive in un gruppo, ne aggiorna lo username.

    Gira in un gruppo di handler separato, così non impedisce agli altri
    handler di elaborare lo stesso messaggio.
    """
    utente = update.effective_user
    chat = update.effective_chat
    if utente is None or chat is None or chat.type not in ("group", "supergroup"):
        return

    with db(context) as conn:
        cambiamento = repository.update_username(conn, utente.id, utente.username)

    if cambiamento is None:
        return

    riga, nuovo = cambiamento
    logger.info(
        "Username aggiornato per il cittadino #%s (Telegram ID %s): %r -> %r",
        riga["citizen_id"],
        utente.id,
        riga["username"],
        nuovo,
    )
    await send_log(
        context,
        f"🔄 *Username aggiornato*\n"
        f"Cittadino: #{riga['citizen_id']} (Telegram ID {utente.id})\n"
        f"{fmt_username(riga['username'])} -> {fmt_username(nuovo)}",
    )


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Registra qualunque eccezione non gestita e avvisa chi ha scritto.

    Senza questo, un errore imprevisto lascerebbe l'utente senza risposta.
    """
    logger.exception("Errore non gestito", exc_info=context.error)
    if isinstance(update, Update):
        try:
            await rispondi(
                update,
                "⚠️ Si è verificato un errore imprevisto. "
                "Riprova, e se persiste avvisa un amministratore.",
            )
        except Exception:  # noqa: BLE001 - non possiamo fare altro
            logger.warning("Impossibile avvisare l'utente dell'errore")


async def catch_all(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Risponde con l'aiuto a comandi sconosciuti e al testo libero in privato."""
    testo = (update.effective_message.text or "").strip() if update.effective_message else ""
    aiuto = render_help(ruolo_utente(update, context))
    if testo.startswith("/"):
        await rispondi(update, f"❓ Comando non riconosciuto.\n\n{aiuto}")
    else:
        await rispondi(update, aiuto)
