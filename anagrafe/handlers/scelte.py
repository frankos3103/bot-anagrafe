"""Le scelte che il wizard legge dal registro invece di farle digitare.

Un `Campo` con `scelte="..."` non ha opzioni fisse: quando il wizard arriva a
quel campo chiama il fornitore corrispondente, che interroga il database e
restituisce le voci da mostrare a pulsanti. Così nessuno deve copiare a mano un
ID numerico.

La `chiave` di ogni Opzione è il testo che il validatore del campo accetta
(«#12» per un cittadino, «7» per un'attività): la scelta a pulsante attraversa
quindi lo stesso percorso di validazione del testo scritto a mano, e le
VERIFICHE_CAMPO continuano a girare dopo. Un pulsante non salta nessun
controllo: se l'attività viene rimossa mentre la tastiera è aperta, la verifica
lo scopre comunque.
"""

from __future__ import annotations

from typing import Awaitable, Callable

from telegram import Update
from telegram.ext import ContextTypes

from .. import repository
from ..commands import Opzione
from ..formatting import cognome_elenco, emoji_attivita
from .common import db, get_roles

Fornitore = Callable[
    [Update, ContextTypes.DEFAULT_TYPE], Awaitable[list[Opzione]]
]


def _etichetta_cittadino(riga) -> str:
    """«Mario ROSSI (@mariorossi)», come negli elenchi."""
    nome = f"{riga['nome']} {cognome_elenco(riga['cognome'])}"
    return f"{nome} (@{riga['username']})" if riga["username"] else nome


async def cittadini(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> list[Opzione]:
    """Tutti i cittadini, in ordine alfabetico.

    La chiave è «#<ID cittadino>»: fissa la persona anche se nel frattempo il
    suo tag passa a qualcun altro, come fa già la verifica di /rimuovi_cittadino.
    """
    with db(context) as conn:
        righe = repository.list_citizens(conn, ordine="nome")
    return [
        Opzione(f"#{r['citizen_id']}", _etichetta_cittadino(r), "👤") for r in righe
    ]


async def amministratori(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> list[Opzione]:
    """Gli amministratori rimovibili: il root non compare, non si rimuove.

    La chiave è l'ID Telegram nudo, che è quello che gli amministratori sono:
    non tutti sono cittadini, quindi non tutti hanno un ID cittadino.
    """
    roles = get_roles(context)
    with db(context) as conn:
        voci = []
        for admin_id in roles.tutti_gli_admin():
            if roles.is_root(admin_id):
                continue
            riga = repository.get_citizen_by_telegram_id(conn, admin_id)
            etichetta = (
                f"{_etichetta_cittadino(riga)}" if riga is not None else str(admin_id)
            )
            voci.append(Opzione(str(admin_id), etichetta, "🛡"))
    return voci


def _etichetta_attivita(riga) -> str:
    return riga["nome_attivita"]


async def attivita_rimovibili(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> list[Opzione]:
    """Le attività che chi sta chiedendo può rimuovere.

    Il proprietario vede le proprie, l'amministratore tutte: è lo stesso
    criterio di controlli.verifica_attivita_rimovibile, perché una tastiera che
    mostrasse voci poi rifiutate sarebbe peggio di nessuna tastiera.
    """
    utente = update.effective_user
    with db(context) as conn:
        if get_roles(context).is_admin(utente.id):
            righe = repository.list_attivita_attive(conn)
        else:
            righe = repository.list_attivita_per_owner(conn, utente.id)
    return [
        Opzione(
            str(r["attivita_id"]),
            _etichetta_attivita(r),
            emoji_attivita(r["tipologia"]),
        )
        for r in righe
    ]


async def attivita_moderabili(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> list[Opzione]:
    """Tutte le attività attive: la moderazione è un atto d'ufficio."""
    with db(context) as conn:
        righe = repository.list_attivita_attive(conn)
    return [
        Opzione(
            str(r["attivita_id"]),
            _etichetta_attivita(r),
            emoji_attivita(r["tipologia"]),
        )
        for r in righe
    ]


FORNITORI: dict[str, Fornitore] = {
    "cittadini": cittadini,
    "amministratori": amministratori,
    "attivita_rimovibili": attivita_rimovibili,
    "attivita_moderabili": attivita_moderabili,
}
