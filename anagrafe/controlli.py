"""Controlli che fanno fallire un'operazione il prima possibile.

Ognuno alza ErroreValidazione con un messaggio mostrabile in chat, oppure
restituisce il valore risolto. Sono usati sia all'inizio dei comandi e a ogni
passo del wizard di /menu (così un'operazione destinata a fallire lo dice
subito), sia dalle azioni stesse, che li ripetono al momento di eseguire.
Nessuna dipendenza da Telegram: si testano da soli.
"""

from __future__ import annotations

import sqlite3

from . import repository
from .roles import RoleRegistry
from .validators import (
    RIF_CITIZEN_ID,
    RIF_NUMERO,
    RIF_TELEGRAM_ID,
    ErroreValidazione,
    Riferimento,
)


def precondizione_richiedi(conn: sqlite3.Connection, telegram_id: int) -> None:
    """Chi è già cittadino o ha una richiesta aperta non può farne un'altra."""
    gia_cittadino = repository.get_citizen_by_telegram_id(conn, telegram_id)
    if gia_cittadino:
        raise ErroreValidazione(f"Sei già cittadino con ID #{gia_cittadino['citizen_id']}.")

    in_attesa = repository.pending_request_for(conn, telegram_id)
    if in_attesa:
        raise ErroreValidazione(
            f"Hai già una richiesta in attesa (#{in_attesa['request_id']}). "
            "Attendi che un amministratore la esamini."
        )


def risolvi_cittadino(conn: sqlite3.Connection, rif: Riferimento) -> sqlite3.Row:
    """Trova il cittadino indicato per #ID, @tag o ID Telegram."""
    if rif.tipo == RIF_NUMERO:
        per_id = repository.get_citizen_by_citizen_id(conn, rif.valore)
        per_telegram = repository.get_citizen_by_telegram_id(conn, rif.valore)
        if per_id and per_telegram and per_id["citizen_id"] != per_telegram["citizen_id"]:
            raise ErroreValidazione(
                f"{rif.valore} è sia l'ID del cittadino #{per_id['citizen_id']} sia "
                f"l'ID Telegram del cittadino #{per_telegram['citizen_id']}: "
                f"scrivi #{rif.valore} per il primo o @username per il secondo."
            )
        riga = per_id or per_telegram
        if riga is None:
            raise ErroreValidazione(
                f"Nessun cittadino con ID cittadino o ID Telegram {rif.valore}."
            )
        return riga

    if rif.tipo == RIF_CITIZEN_ID:
        riga = repository.get_citizen_by_citizen_id(conn, rif.valore)
    elif rif.tipo == RIF_TELEGRAM_ID:
        riga = repository.get_citizen_by_telegram_id(conn, rif.valore)
    else:
        righe = repository.get_citizens_by_username(conn, rif.valore)
        if len(righe) > 1:
            elenco = ", ".join(f"#{r['citizen_id']}" for r in righe)
            raise ErroreValidazione(
                f"Il tag {rif} è associato a più cittadini ({elenco}): usa l'ID cittadino."
            )
        riga = righe[0] if righe else None

    if riga is None:
        raise ErroreValidazione(f"Nessun cittadino trovato per {rif}.")
    return riga


def risolvi_telegram_id(conn: sqlite3.Connection, rif: Riferimento) -> int:
    """L'ID Telegram indicato direttamente o tramite il tag/ID di un cittadino."""
    if rif.tipo == RIF_TELEGRAM_ID:
        return rif.valore
    return risolvi_cittadino(conn, rif)["telegram_id"]


def verifica_nuovo_cittadino(conn: sqlite3.Connection, telegram_id: int) -> None:
    esistente = repository.get_citizen_by_telegram_id(conn, telegram_id)
    if esistente:
        raise ErroreValidazione(
            f"Questo ID Telegram è già registrato come cittadino #{esistente['citizen_id']}."
        )


def verifica_nuovo_admin(roles: RoleRegistry, telegram_id: int) -> None:
    if roles.is_root(telegram_id):
        raise ErroreValidazione(
            "Questo ID è già il root e dispone automaticamente dei privilegi "
            "di amministratore."
        )
    if roles.is_admin(telegram_id):
        raise ErroreValidazione(f"L'ID Telegram {telegram_id} è già un amministratore.")


def verifica_admin_rimovibile(roles: RoleRegistry, telegram_id: int) -> None:
    if roles.is_root(telegram_id):
        raise ErroreValidazione(
            "Il root non può essere rimosso dall'elenco degli amministratori."
        )
    if not roles.is_admin(telegram_id):
        raise ErroreValidazione(
            f"L'ID Telegram {telegram_id} non risulta nell'elenco degli amministratori."
        )


# ----------------------------------------------------------------------
# Registro delle attività
# ----------------------------------------------------------------------

def precondizione_attivita(conn: sqlite3.Connection, telegram_id: int) -> sqlite3.Row:
    """Il Registro delle Attività è riservato ai cittadini già iscritti.

    È il requisito di cittadinanza del Decreto Ministeriale n.3 del 13/10/2026,
    ed è anche il motivo per cui attivita.owner_id non ha una FOREIGN KEY
    (vedi il commento allo schema in db.py). Restituisce la riga del cittadino,
    che serve poi per la scheda pubblica e per la notifica al Ministero.
    """
    cittadino = repository.get_citizen_by_telegram_id(conn, telegram_id)
    if cittadino is None:
        raise ErroreValidazione(
            "Il Registro Pubblico delle Attività è riservato ai cittadini "
            "della Repubblica. Non risulti iscritto all'anagrafe: invia prima "
            "una richiesta di cittadinanza con /richiedi."
        )
    return cittadino


def verifica_nome_attivita_libero(
    conn: sqlite3.Connection, owner_id: int, nome_attivita: str
) -> str:
    """Restituisce il nome se il proprietario non ne ha già una così chiamata.

    Il vincolo è per proprietario e solo fra le attività attive: due cittadini
    diversi possono avere attività omonime, e un nome torna libero dopo una
    rimozione d'ufficio.
    """
    esistente = repository.attivita_per_nome(conn, owner_id, nome_attivita)
    if esistente is not None:
        raise ErroreValidazione(
            f"Hai già registrato un'attività con il nome "
            f"«{esistente['nome_attivita']}» (#{esistente['attivita_id']}). "
            "Scegli un nome diverso."
        )
    return nome_attivita


def risolvi_attivita(conn: sqlite3.Connection, attivita_id: int) -> sqlite3.Row:
    riga = repository.get_attivita(conn, attivita_id)
    if riga is None:
        raise ErroreValidazione(f"Nessuna attività con ID #{attivita_id}.")
    return riga


def verifica_attivita_moderabile(
    conn: sqlite3.Connection, attivita_id: int
) -> sqlite3.Row:
    """L'attività esiste e non è ancora stata moderata.

    Serve a dirlo subito all'amministratore; la garanzia vera contro la doppia
    moderazione è l'UPDATE condizionato di repository.chiudi_attivita.
    """
    riga = risolvi_attivita(conn, attivita_id)
    if riga["stato"] != repository.ATTIVITA_ATTIVA:
        etichetta = repository.ETICHETTE_STATO_ATTIVITA.get(
            riga["stato"], riga["stato"]
        )
        raise ErroreValidazione(
            f"L'attività #{attivita_id} è già {etichetta}."
        )
    return riga
