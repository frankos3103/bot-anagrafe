"""Pubblicazione del Registro delle Attività sulla Gazzetta Ciompista.

Stesso contratto di logbook.send_log: queste funzioni non sollevano mai. Se il
canale non è configurato, il bot non ne è amministratore o il post non è più
raggiungibile, l'errore viene solo registrato nei log locali. La verità sta
nella tabella `attivita`: la Gazzetta ne è una vista, e un problema di canale
non deve far fallire né l'iscrizione né la moderazione.
"""

from __future__ import annotations

import logging
from typing import Mapping

from telegram.error import TelegramError
from telegram.ext import ContextTypes

from ..formatting import post_gazzetta, post_gazzetta_rimosso

logger = logging.getLogger(__name__)

# Esiti di chiudi_post(): il chiamante deve saper distinguere il post cancellato
# (il riferimento va azzerato) da quello solo riscritto, e sapere quando
# avvisare l'amministratore che in Gazzetta è rimasta una voce da togliere.
POST_CANCELLATO = "cancellato"
POST_MODIFICATO = "modificato"
POST_ASSENTE = "assente"
POST_FALLITO = "fallito"


def canale_gazzetta(context: ContextTypes.DEFAULT_TYPE) -> int | str | None:
    """Il canale configurato, o None se la pubblicazione è disattivata."""
    settings = context.bot_data.get("settings")
    return getattr(settings, "gazzetta_channel_id", None)


async def pubblica_attivita(
    context: ContextTypes.DEFAULT_TYPE, riga: Mapping
) -> tuple[str, int] | None:
    """Pubblica la scheda di un'attività e restituisce (chat_id, message_id).

    None se il canale non è configurato o l'invio è fallito: l'attività resta
    comunque iscritta al Registro, e chi l'ha registrata lo viene a sapere dal
    messaggio di conferma.
    """
    canale = canale_gazzetta(context)
    if not canale:
        return None

    try:
        inviato = await context.bot.send_message(
            chat_id=canale,
            text=post_gazzetta(riga),
            parse_mode="MarkdownV2",
            disable_web_page_preview=True,
        )
    except TelegramError as exc:
        logger.warning(
            "Impossibile pubblicare l'attività #%s sulla Gazzetta %s: %s",
            riga["attivita_id"],
            canale,
            exc,
        )
        return None

    return str(inviato.chat_id), inviato.message_id


async def chiudi_post(context: ContextTypes.DEFAULT_TYPE, riga: Mapping) -> str:
    """Toglie dalla Gazzetta il post di un'attività moderata.

    Si tenta prima la cancellazione, che è l'esito voluto: l'elenco pubblico
    resta pulito e contiene solo attività attive. Se non è più possibile (un
    post oltre le 48 ore, il bot rimosso dal canale) si ricade sulla
    riscrittura, che per un messaggio del bot non ha limiti di tempo. POST_FALLITO
    solo se non si è riusciti in nessuno dei due modi.
    """
    message_id = riga["message_id_pubblico"]
    if not message_id:
        # Il canale non era configurato quando l'attività è stata iscritta.
        return POST_ASSENTE

    chat_id = riga["chat_id_pubblico"] or canale_gazzetta(context)
    if not chat_id:
        return POST_ASSENTE

    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
        return POST_CANCELLATO
    except TelegramError as exc:
        logger.warning(
            "Non ho potuto cancellare il post dell'attività #%s (chat %s, msg %s): "
            "%s. Provo a riscriverlo.",
            riga["attivita_id"],
            chat_id,
            message_id,
            exc,
        )

    try:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=post_gazzetta_rimosso(riga),
            parse_mode="MarkdownV2",
            disable_web_page_preview=True,
        )
        return POST_MODIFICATO
    except TelegramError as exc:
        logger.warning(
            "Non ho potuto nemmeno riscrivere il post dell'attività #%s "
            "(chat %s, msg %s): %s",
            riga["attivita_id"],
            chat_id,
            message_id,
            exc,
        )
        return POST_FALLITO
