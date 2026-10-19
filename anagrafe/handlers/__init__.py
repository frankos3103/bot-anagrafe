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
from .attivita import (
    cmd_elenco_attivita,
    cmd_esporta_attivita,
    cmd_modera_attivita,
    cmd_rimuovi_attivita,
    on_attivita_callback,
)
from .importazione import cmd_importa_attivita, cmd_importa_cittadini, on_documento
from .menu import build_menu_handler
from .misc import aggiorna_tag, catch_all, on_error
from .richieste import on_richiesta_callback

COMANDI = {
    "start": comandi.cmd_start,
    "help": comandi.cmd_help,
    "elenco_cittadini": comandi.cmd_elenco_cittadini,
    "esporta_cittadini": comandi.cmd_esporta_cittadini,
    "cerca_cittadino": comandi.cmd_cerca_cittadino,
    "richiedi_cittadinanza": comandi.cmd_richiedi_cittadinanza,
    "inserisci_cittadino": comandi.cmd_inserisci_cittadino,
    "rimuovi_cittadino": comandi.cmd_rimuovi_cittadino,
    "tagga_cittadini": comandi.cmd_tagga_cittadini,
    "importa_cittadini": cmd_importa_cittadini,
    "aggiungi_admin": comandi.cmd_aggiungi_admin,
    "rimuovi_admin": comandi.cmd_rimuovi_admin,
    "elenco_admin": comandi.cmd_elenco_admin,
    "elenco_attivita": cmd_elenco_attivita,
    "rimuovi_attivita": cmd_rimuovi_attivita,
    "esporta_attivita": cmd_esporta_attivita,
    "importa_attivita": cmd_importa_attivita,
    "modera_attivita": cmd_modera_attivita,
    # «attivita» NON va qui: ha wizard_diretto=True, quindi sta negli
    # entry_points di build_menu_handler(). La ConversationHandler è
    # registrata prima dei CommandHandler, perciò un CommandHandler omonimo
    # verrebbe registrato ma mai raggiunto.
}


def registra_handlers(application: Application) -> None:
    # 0. Il tag di chi scrive, aggiornato prima di tutto il resto.
    application.add_handler(TypeHandler(Update, aggiorna_tag), group=-1)

    # 1. La pulsantiera, che ha la precedenza perché gestisce una conversazione.
    application.add_handler(build_menu_handler())

    # 2. I comandi testuali.
    for nome, funzione in COMANDI.items():
        application.add_handler(CommandHandler(nome, funzione))

    # 3. I pulsanti delle richieste di cittadinanza e della moderazione delle
    #    attività. I pattern sono disgiunti fra loro e da quelli della
    #    pulsantiera (tutti prefissati «menu:»), quindi l'ordine è indifferente.
    application.add_handler(
        CallbackQueryHandler(on_richiesta_callback, pattern=r"^richiesta:")
    )
    application.add_handler(
        CallbackQueryHandler(on_attivita_callback, pattern=r"^attivita:")
    )

    # 4. Gli allegati (import CSV). Solo messaggi di utenti: un MessageHandler
    #    con filtri espliciti riceve anche i post dei canali in cui il bot è
    #    amministratore, e ogni file pubblicato lì finirebbe qui.
    application.add_handler(
        MessageHandler(filters.UpdateType.MESSAGE & filters.Document.ALL, on_documento)
    )

    # 5. Catch-all: comandi sconosciuti ovunque, testo libero solo in privato
    #    (altrimenti il bot risponderebbe a ogni chiacchiera di gruppo).
    application.add_handler(
        MessageHandler(
            filters.UpdateType.MESSAGE
            & (filters.COMMAND | (filters.ChatType.PRIVATE & filters.TEXT)),
            catch_all,
        )
    )

    # Rete di sicurezza per le eccezioni non gestite.
    application.add_error_handler(on_error)


__all__ = ["registra_handlers"]
