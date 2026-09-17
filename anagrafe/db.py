"""Accesso al database SQLite: connessione, schema, migrazioni leggere."""

from __future__ import annotations

import logging
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

logger = logging.getLogger(__name__)


def get_connection(db_path: Path | str) -> sqlite3.Connection:
    """Apre una connessione con le righe accessibili per nome di colonna."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def apri_db(db_path: Path | str) -> Iterator[sqlite3.Connection]:
    """Context manager che chiude davvero la connessione.

    `with sqlite3.connect(...) as conn` gestisce solo la transazione: la
    connessione resterebbe aperta. Qui la chiudiamo sempre.
    """
    conn = get_connection(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


SCHEMA_CITTADINI = """
CREATE TABLE IF NOT EXISTS cittadini (
    telegram_id       INTEGER NOT NULL,
    citizen_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    username          TEXT,
    nome              TEXT NOT NULL,
    cognome           TEXT NOT NULL,
    data_acquisizione TEXT NOT NULL
)
"""

SCHEMA_RICHIESTE = """
CREATE TABLE IF NOT EXISTS richieste (
    request_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id     INTEGER NOT NULL,
    username        TEXT,
    nome            TEXT NOT NULL,
    cognome         TEXT NOT NULL,
    data_richiesta  TEXT NOT NULL,
    stato           TEXT NOT NULL DEFAULT 'in_attesa',
    admin_id        INTEGER,
    admin_username  TEXT,
    data_gestione   TEXT,
    notifiche       TEXT
)
"""


def init_db(db_path: Path | str) -> None:
    """Crea le tabelle se non esistono e prova ad aggiungere l'indice unico.

    Lo schema delle tabelle è identico a quello delle versioni precedenti: un
    registro.db già esistente continua a funzionare senza migrazioni.
    """
    with apri_db(db_path) as conn:
        conn.execute(SCHEMA_CITTADINI)
        conn.execute(SCHEMA_RICHIESTE)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_richieste_stato "
            "ON richieste(telegram_id, stato)"
        )
        try:
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_cittadini_telegram_id "
                "ON cittadini(telegram_id)"
            )
        except sqlite3.IntegrityError:
            # Un database preesistente potrebbe contenere doppioni: non è un
            # motivo per impedire l'avvio, ma va segnalato.
            logger.warning(
                "Impossibile creare l'indice unico su cittadini.telegram_id: "
                "nel registro esistono ID Telegram duplicati. Rimuovili con "
                "/rimuovi per attivare la protezione contro i doppioni."
            )
