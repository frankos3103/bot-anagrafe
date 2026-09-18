"""Handler di contorno: aggiornamento automatico dei tag e catch-all."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from .. import repository
from ..commands import render_help
from ..logbook import fmt_username, send_log
from .common import db, rispondi, ruolo_utente

logger = logging.getLogger(__name__)


async def aggiorna_tag(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """A ogni interazione con il bot registra il tag attuale di chi scrive.

    Gira su qualunque update (messaggi in privato e nei gruppi, pulsanti) in un
    gruppo di handler che precede tutti gli altri, così un comando che usa il
    tag trova già il valore aggiornato, e non impedisce ad altri handler di
    elaborare lo stesso update.
    """
    utente = update.effective_user
    if utente is None or utente.is_bot:
        return

    with db(context) as conn:
        cambiamento = repository.update_username(conn, utente.id, utente.username)

    if cambiamento is None:
        return

    for vecchio in cambiamento.sottratto_a:
        logger.info(
            "Tag @%s tolto al cittadino #%s: ora appartiene a Telegram ID %s",
            vecchio["username"],
            vecchio["citizen_id"],
            utente.id,
        )
        await send_log(
            context,
            f"🔄 *Username non più valido*\n"
            f"Cittadino: #{vecchio['citizen_id']} (Telegram ID {vecchio['telegram_id']})\n"
            f"{fmt_username(vecchio['username'])} ora appartiene a Telegram ID {utente.id}",
        )

    riga = cambiamento.riga
    if riga is None:
        return

    logger.info(
        "Username aggiornato per il cittadino #%s (Telegram ID %s): %r -> %r",
        riga["citizen_id"],
        utente.id,
        riga["username"],
        cambiamento.nuovo,
    )
    await send_log(
        context,
        f"🔄 *Username aggiornato*\n"
        f"Cittadino: #{riga['citizen_id']} (Telegram ID {utente.id})\n"
        f"{fmt_username(riga['username'])} -> {fmt_username(cambiamento.nuovo)}",
    )


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Registra qualunque eccezione non gestita e avvisa chi ha scritto.

    Senza questo, un errore imprevisto lascerebbe l'utente senza risposta.
    """
    logger.exception("Errore non gestito", exc_info=context.error)
    # In un canale non c'è nessuno da avvisare: la risposta finirebbe
    # pubblicata sotto il post.
    if isinstance(update, Update) and not (
        update.effective_chat and update.effective_chat.type == "channel"
    ):
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
