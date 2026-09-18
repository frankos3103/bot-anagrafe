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
