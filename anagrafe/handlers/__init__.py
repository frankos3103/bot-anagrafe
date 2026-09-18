"""Registrazione degli handler sull'applicazione Telegram.

L'ordine conta. Gli handler stanno in due gruppi:

  gruppo -1 — l'aggiornamento automatico dei tag, che deve vedere *tutti* gli
              update (privati, gruppi, pulsanti) prima che vengano elaborati,
              senza impedire agli altri handler di farlo.
  gruppo 0  — comandi, pulsanti e, per ultimo, il catch-all che risponde ai
              comandi sconosciuti. Dentro un gruppo Telegram elabora al massimo
              un handler, quindi il catch-all scatta solo se nient'altro ha
              raccolto il messaggio.
"""

from __future__ import annotations

from telegram import Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    TypeHandler,
    filters,
)

from . import comandi
from .importazione import cmd_importa, on_documento
from .menu import build_menu_handler
from .misc import aggiorna_tag, catch_all, on_error
from .richieste import on_richiesta_callback

COMANDI = {
    "start": comandi.cmd_start,
    "help": comandi.cmd_help,
    "elenco": comandi.cmd_elenco,
    "esporta": comandi.cmd_esporta,
    "cerca": comandi.cmd_cerca,
    "richiedi": comandi.cmd_richiedi,
    "inserisci": comandi.cmd_inserisci,
    "rimuovi": comandi.cmd_rimuovi,
    "importa": cmd_importa,
    "aggiungi_admin": comandi.cmd_aggiungi_admin,
    "rimuovi_admin": comandi.cmd_rimuovi_admin,
    "elenco_admin": comandi.cmd_elenco_admin,
}


def registra_handlers(application: Application) -> None:
    # 0. Il tag di chi scrive, aggiornato prima di tutto il resto.
    application.add_handler(TypeHandler(Update, aggiorna_tag), group=-1)

    # 1. La pulsantiera, che ha la precedenza perché gestisce una conversazione.
    application.add_handler(build_menu_handler())

    # 2. I comandi testuali.
    for nome, funzione in COMANDI.items():
        application.add_handler(CommandHandler(nome, funzione))

    # 3. I pulsanti delle richieste di cittadinanza.
    application.add_handler(
        CallbackQueryHandler(on_richiesta_callback, pattern=r"^richiesta:")
    )

    # 4. Gli allegati (import CSV).
    application.add_handler(MessageHandler(filters.Document.ALL, on_documento))

    # 5. Catch-all: comandi sconosciuti ovunque, testo libero solo in privato
    #    (altrimenti il bot risponderebbe a ogni chiacchiera di gruppo).
    application.add_handler(
        MessageHandler(
            filters.COMMAND | (filters.ChatType.PRIVATE & filters.TEXT), catch_all
        )
    )

    # Rete di sicurezza per le eccezioni non gestite.
    application.add_error_handler(on_error)


__all__ = ["registra_handlers"]
