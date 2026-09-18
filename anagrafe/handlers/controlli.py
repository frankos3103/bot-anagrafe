"""Aggancia i controlli di anagrafe.controlli al wizard e ai comandi testuali.

PRECONDIZIONI[comando] gira prima di chiedere qualunque dato: se fallisce,
il wizard non parte nemmeno. VERIFICHE_CAMPO[(comando, chiave)] gira appena
l'utente ha fornito quel campo, e può sostituire il valore con la sua forma
risolta (es. @mario -> #12), che è quella mostrata nel riepilogo ed eseguita.
Tutte alzano ErroreValidazione con un messaggio da mostrare in chat.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from telegram import Update
from telegram.ext import ContextTypes

from .. import controlli
from ..validators import RIF_CITIZEN_ID, RIF_TELEGRAM_ID, Riferimento
from .common import db, get_roles

Precondizione = Callable[[Update, ContextTypes.DEFAULT_TYPE], Awaitable[None]]
Verifica = Callable[[Update, ContextTypes.DEFAULT_TYPE, Any], Awaitable[Any]]


async def _pre_richiedi(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    with db(context) as conn:
        controlli.precondizione_richiedi(conn, update.effective_user.id)


async def _verifica_inserisci(
    update: Update, context: ContextTypes.DEFAULT_TYPE, telegram_id: int
) -> int:
    with db(context) as conn:
        controlli.verifica_nuovo_cittadino(conn, telegram_id)
    return telegram_id


async def _verifica_rimuovi(
    update: Update, context: ContextTypes.DEFAULT_TYPE, rif: Riferimento
) -> Riferimento:
    with db(context) as conn:
        riga = controlli.risolvi_cittadino(conn, rif)
    # Si fissa l'ID cittadino: se nel frattempo il tag passa ad altri, si
    # rimuove comunque chi l'utente ha visto nel riepilogo.
    return Riferimento(RIF_CITIZEN_ID, riga["citizen_id"])


async def _risolvi_utente(context: ContextTypes.DEFAULT_TYPE, rif: Riferimento) -> int:
    with db(context) as conn:
        return controlli.risolvi_telegram_id(conn, rif)


async def _verifica_aggiungi_admin(
    update: Update, context: ContextTypes.DEFAULT_TYPE, rif: Riferimento
) -> Riferimento:
    telegram_id = await _risolvi_utente(context, rif)
    controlli.verifica_nuovo_admin(get_roles(context), telegram_id)
    return Riferimento(RIF_TELEGRAM_ID, telegram_id)


async def _verifica_rimuovi_admin(
    update: Update, context: ContextTypes.DEFAULT_TYPE, rif: Riferimento
) -> Riferimento:
    telegram_id = await _risolvi_utente(context, rif)
    controlli.verifica_admin_rimovibile(get_roles(context), telegram_id)
    return Riferimento(RIF_TELEGRAM_ID, telegram_id)


PRECONDIZIONI: dict[str, Precondizione] = {
    "richiedi": _pre_richiedi,
}

VERIFICHE_CAMPO: dict[tuple[str, str], Verifica] = {
    ("inserisci", "telegram_id"): _verifica_inserisci,
    ("rimuovi", "cittadino"): _verifica_rimuovi,
    ("aggiungi_admin", "utente"): _verifica_aggiungi_admin,
    ("rimuovi_admin", "utente"): _verifica_rimuovi_admin,
}
