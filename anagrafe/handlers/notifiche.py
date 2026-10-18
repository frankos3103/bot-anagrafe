"""Notifiche di controllo agli amministratori: invio, aggiornamento, avvisi.

Una notifica va in DM a ogni amministratore e, più tardi, tutte le copie vanno
riscritte con l'esito, così chi non ha cliccato vede comunque com'è andata. Lo
fanno sia le richieste di cittadinanza sia il Registro delle Attività: il codice
sta qui una volta sola, con le coppie (chat_id, message_id) persistite nella
colonna «notifiche» della rispettiva tabella.
"""

from __future__ import annotations

import logging
from typing import Iterable

from telegram import InlineKeyboardMarkup
from telegram.error import Forbidden, TelegramError
from telegram.ext import ContextTypes

from .. import repository

logger = logging.getLogger(__name__)


async def invia_notifiche_admin(
    context: ContextTypes.DEFAULT_TYPE,
    admin_ids: Iterable[int],
    testo: str,
    tastiera: InlineKeyboardMarkup | None = None,
) -> tuple[list[list[int]], list[int]]:
    """Manda la stessa notifica in DM a ogni amministratore.

    Restituisce (notifiche, non_raggiungibili): la prima lista, di coppie
    [chat_id, message_id], è quella da salvare nella colonna «notifiche» per
    poter poi aggiornare tutte le copie. Un amministratore irraggiungibile non
    fa fallire l'operazione: viene solo riportato a chi chiama.
    """
    notifiche: list[list[int]] = []
    non_raggiungibili: list[int] = []

    for admin_id in admin_ids:
        try:
            inviato = await context.bot.send_message(
                chat_id=admin_id, text=testo, reply_markup=tastiera
            )
            notifiche.append([inviato.chat_id, inviato.message_id])
        except Forbidden:
            # L'admin non ha mai avviato una chat privata con il bot.
            non_raggiungibili.append(admin_id)
            logger.warning(
                "Impossibile notificare l'admin %s: deve avviare prima una chat "
                "privata con il bot (/start).",
                admin_id,
            )
        except TelegramError as exc:
            non_raggiungibili.append(admin_id)
            logger.warning(
                "Errore inviando la notifica all'admin %s: %s", admin_id, exc
            )

    return notifiche, non_raggiungibili


async def aggiorna_copie_notifica(
    context: ContextTypes.DEFAULT_TYPE,
    notifiche_json: str | None,
    testo_finale: str,
    salta: tuple[int, int] | None = None,
) -> None:
    """Aggiorna la copia della notifica ricevuta da ogni admin.

    Così tutti vedono l'esito, non solo chi ha cliccato. `salta` evita di
    modificare due volte il messaggio già aggiornato sulla query.
    """
    for chat_id, message_id in repository.load_notifiche(notifiche_json):
        if salta and (chat_id, message_id) == salta:
            continue
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=testo_finale,
                reply_markup=InlineKeyboardMarkup([]),
            )
        except TelegramError as exc:
            logger.warning(
                "Impossibile aggiornare la notifica in chat %s (msg %s): %s",
                chat_id,
                message_id,
                exc,
            )


async def avvisa_in_privato(
    context: ContextTypes.DEFAULT_TYPE, telegram_id: int, testo: str
) -> None:
    """Avvisa un utente in privato, senza far fallire nulla se non si può.

    Il destinatario potrebbe non aver mai avviato il bot in chat privata.
    """
    try:
        await context.bot.send_message(chat_id=telegram_id, text=testo)
    except TelegramError:
        pass
