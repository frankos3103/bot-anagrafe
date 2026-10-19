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


async def _pre_attivita(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    with db(context) as conn:
        controlli.precondizione_attivita(conn, update.effective_user.id)


async def _verifica_nome_attivita(
    update: Update, context: ContextTypes.DEFAULT_TYPE, nome: str
) -> str:
    with db(context) as conn:
        return controlli.verifica_nome_attivita_libero(
            conn, update.effective_user.id, nome
        )


async def _verifica_attivita_rimovibile(
    update: Update, context: ContextTypes.DEFAULT_TYPE, attivita_id: int
) -> int:
    """Chi indica un'attività non sua lo scopre al primo passo del wizard."""
    e_admin = get_roles(context).is_admin(update.effective_user.id)
    with db(context) as conn:
        controlli.verifica_attivita_rimovibile(
            conn, attivita_id, update.effective_user.id, e_admin
        )
    return attivita_id


async def _verifica_attivita_moderabile(
    update: Update, context: ContextTypes.DEFAULT_TYPE, attivita_id: int
) -> int:
    with db(context) as conn:
        controlli.verifica_attivita_moderabile(conn, attivita_id)
    return attivita_id


PRECONDIZIONI: dict[str, Precondizione] = {
    "richiedi_cittadinanza": _pre_richiedi,
    "registra_attivita": _pre_attivita,
}

VERIFICHE_CAMPO: dict[tuple[str, str], Verifica] = {
    ("inserisci_cittadino", "telegram_id"): _verifica_inserisci,
    ("rimuovi_cittadino", "cittadino"): _verifica_rimuovi,
    ("aggiungi_admin", "utente"): _verifica_aggiungi_admin,
    ("rimuovi_admin", "utente"): _verifica_rimuovi_admin,
    ("registra_attivita", "nome_attivita"): _verifica_nome_attivita,
    ("modera_attivita", "attivita"): _verifica_attivita_moderabile,
    ("rimuovi_attivita", "attivita"): _verifica_attivita_rimovibile,
}
