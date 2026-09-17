"""Utilità condivise dagli handler: accesso a settings/ruoli e guardie di ruolo."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from functools import wraps
from typing import Iterator

from telegram import Update
from telegram.ext import ContextTypes

from ..config import Settings
from ..db import apri_db
from ..roles import Role, RoleRegistry

MESSAGGIO_NEGATO = {
    Role.ADMIN: "⛔ Non sei autorizzato a usare questo comando.",
    Role.ROOT: "⛔ Comando riservato all'utente root.",
}


def get_settings(context: ContextTypes.DEFAULT_TYPE) -> Settings:
    return context.bot_data["settings"]


def get_roles(context: ContextTypes.DEFAULT_TYPE) -> RoleRegistry:
    return context.bot_data["roles"]


def ruolo_utente(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Role:
    utente = update.effective_user
    if utente is None:
        return Role.PUBBLICO
    return get_roles(context).role_of(utente.id)


@contextmanager
def db(context: ContextTypes.DEFAULT_TYPE) -> Iterator[sqlite3.Connection]:
    """Apre una connessione al registro configurato."""
    with apri_db(get_settings(context).db_path) as conn:
        yield conn


async def rispondi(update: Update, testo: str, **kwargs) -> None:
    """Risponde al messaggio corrente, che arrivi da un comando o da un pulsante.

    Passando da un callback query `update.message` è None: usiamo sempre
    `effective_message`.
    """
    messaggio = update.effective_message
    if messaggio is not None:
        await messaggio.reply_text(testo, **kwargs)


def richiede(ruolo_minimo: Role):
    """Decoratore: blocca l'handler se l'utente non ha il ruolo richiesto."""

    def decoratore(funzione):
        @wraps(funzione)
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *a, **kw):
            if ruolo_utente(update, context) < ruolo_minimo:
                await rispondi(update, MESSAGGIO_NEGATO[ruolo_minimo])
                return None
            return await funzione(update, context, *a, **kw)

        return wrapper

    return decoratore
