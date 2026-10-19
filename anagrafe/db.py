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


# owner_id è l'ID Telegram del proprietario, ma NON è dichiarato FOREIGN KEY
# verso cittadini(telegram_id): quella colonna non è la primary key e il suo
# indice unico può mancare sui registri preesistenti con ID duplicati (vedi
# init_db). Con PRAGMA foreign_keys = ON una FK verso una colonna non unica fa
# fallire ogni INSERT con «foreign key mismatch», e senza ON DELETE bloccherebbe
# /rimuovi_cittadino per i cittadini con attività. Il vincolo di cittadinanza è applicato
# in controlli.precondizione_attivita, come già accade per la tabella richieste.
SCHEMA_ATTIVITA = """
CREATE TABLE IF NOT EXISTS attivita (
    attivita_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id            INTEGER NOT NULL,
    owner_username      TEXT,
    nome_attivita       TEXT NOT NULL,
    tipologia           TEXT NOT NULL,
    descrizione         TEXT NOT NULL,
    contatto_link       TEXT,
    stato               TEXT NOT NULL DEFAULT 'ATTIVA',
    chat_id_pubblico    TEXT,
    message_id_pubblico INTEGER,
    created_at          TEXT NOT NULL,
    admin_id            INTEGER,
    admin_username      TEXT,
    data_moderazione    TEXT,
    notifiche           TEXT
)
"""


# Le proposte in attesa di approvazione. Una riga esiste *solo* mentre la
# proposta è pendente: approvarla la sposta in «attivita», rifiutarla la
# cancella. Non c'è una colonna di stato perché non ci sono stati: questo
# rende la DELETE stessa il lock contro due amministratori che decidono
# insieme (vedi repository.approva_proposta).
SCHEMA_PROPOSTE_ATTIVITA = """
CREATE TABLE IF NOT EXISTS proposte_attivita (
    proposta_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id       INTEGER NOT NULL,
    owner_username TEXT,
    nome_attivita  TEXT NOT NULL,
    tipologia      TEXT NOT NULL,
    descrizione    TEXT NOT NULL,
    contatto_link  TEXT,
    created_at     TEXT NOT NULL,
    notifiche      TEXT
)
"""


def init_db(db_path: Path | str) -> None:
    """Crea le tabelle se non esistono e prova ad aggiungere gli indici unici.

    Lo schema delle tabelle è identico a quello delle versioni precedenti: un
    registro.db già esistente continua a funzionare senza migrazioni.
    """
    with apri_db(db_path) as conn:
        conn.execute(SCHEMA_CITTADINI)
        conn.execute(SCHEMA_RICHIESTE)
        conn.execute(SCHEMA_ATTIVITA)
        conn.execute(SCHEMA_PROPOSTE_ATTIVITA)
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
                "/rimuovi_cittadino per attivare la protezione contro i doppioni."
            )

        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_attivita_stato ON attivita(stato)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_attivita_owner "
            "ON attivita(owner_id, stato)"
        )
        try:
            # Rete di sicurezza per la regola «un nome per proprietario»: essendo
            # un indice parziale vale solo fra le attività ATTIVE, così un nome
            # torna libero dopo una rimozione d'ufficio.
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_attivita_nome_owner "
                "ON attivita(owner_id, nome_attivita COLLATE NOCASE) "
                "WHERE stato = 'ATTIVA'"
            )
        except sqlite3.IntegrityError:
            logger.warning(
                "Impossibile creare l'indice unico su "
                "attivita(owner_id, nome_attivita): nel registro esistono "
                "attività attive con lo stesso nome e lo stesso proprietario."
            )

        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_proposte_owner "
            "ON proposte_attivita(owner_id)"
        )
        try:
            # Tutte le proposte sono pendenti, quindi qui l'indice unico non ha
            # bisogno di essere parziale come quello su «attivita».
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_proposte_nome_owner "
                "ON proposte_attivita(owner_id, nome_attivita COLLATE NOCASE)"
            )
        except sqlite3.IntegrityError:
            logger.warning(
                "Impossibile creare l'indice unico su "
                "proposte_attivita(owner_id, nome_attivita): esistono proposte "
                "con lo stesso nome e lo stesso proprietario."
            )
