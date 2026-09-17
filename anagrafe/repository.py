"""Tutte le query sul registro. Nessuna dipendenza da Telegram: si testa da sola."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

from .validators import normalizza_username

STATO_IN_ATTESA = "in_attesa"
STATO_ACCETTATA = "accettata"
STATO_RIFIUTATA = "rifiutata"


class CittadinoGiaEsistente(Exception):
    """Il telegram_id è già presente nel registro."""

    def __init__(self, citizen_id: int) -> None:
        super().__init__(f"Telegram ID già registrato come cittadino #{citizen_id}")
        self.citizen_id = citizen_id


def oggi() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


# ----------------------------------------------------------------------
# Cittadini
# ----------------------------------------------------------------------

def get_citizen_by_telegram_id(conn: sqlite3.Connection, telegram_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM cittadini WHERE telegram_id = ?", (telegram_id,)
    ).fetchone()


def get_citizen_by_citizen_id(conn: sqlite3.Connection, citizen_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM cittadini WHERE citizen_id = ?", (citizen_id,)
    ).fetchone()


def list_citizens(conn: sqlite3.Connection, ordine: str = "citizen_id") -> list[sqlite3.Row]:
    """ordine: 'citizen_id' (ordine di registrazione) oppure 'nome' (alfabetico)."""
    if ordine == "nome":
        sql = "SELECT * FROM cittadini ORDER BY nome COLLATE NOCASE, cognome COLLATE NOCASE"
    else:
        sql = "SELECT * FROM cittadini ORDER BY citizen_id ASC"
    return conn.execute(sql).fetchall()


def count_citizens(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) AS n FROM cittadini").fetchone()["n"]


def search_citizens(conn: sqlite3.Connection, query: str) -> list[sqlite3.Row]:
    """Cerca la stringa in nome, cognome, username o ID Telegram."""
    pattern = f"%{query.strip()}%"
    return conn.execute(
        """
        SELECT * FROM cittadini
        WHERE nome LIKE ? COLLATE NOCASE
           OR cognome LIKE ? COLLATE NOCASE
           OR username LIKE ? COLLATE NOCASE
           OR CAST(telegram_id AS TEXT) LIKE ?
        ORDER BY citizen_id ASC
        """,
        (pattern, pattern, pattern, pattern),
    ).fetchall()


def insert_citizen(
    conn: sqlite3.Connection,
    telegram_id: int,
    username: str | None,
    nome: str,
    cognome: str,
    data_acquisizione: str | None = None,
) -> int:
    """Inserisce un cittadino e ne restituisce il citizen_id.

    Alza CittadinoGiaEsistente se quel telegram_id è già nel registro.
    """
    esistente = get_citizen_by_telegram_id(conn, telegram_id)
    if esistente:
        raise CittadinoGiaEsistente(esistente["citizen_id"])

    cursore = conn.execute(
        """
        INSERT INTO cittadini (telegram_id, username, nome, cognome, data_acquisizione)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            telegram_id,
            normalizza_username(username),
            nome,
            cognome,
            data_acquisizione or oggi(),
        ),
    )
    conn.commit()
    return cursore.lastrowid


def delete_citizen(conn: sqlite3.Connection, citizen_id: int) -> sqlite3.Row | None:
    """Cancella il cittadino e restituisce la riga cancellata (None se assente)."""
    row = get_citizen_by_citizen_id(conn, citizen_id)
    if row is None:
        return None
    conn.execute("DELETE FROM cittadini WHERE citizen_id = ?", (citizen_id,))
    conn.commit()
    return row


def update_username(
    conn: sqlite3.Connection, telegram_id: int, username: str | None
) -> tuple[sqlite3.Row, str | None] | None:
    """Aggiorna lo username di un cittadino.

    Restituisce (riga_precedente, nuovo_username) se qualcosa è cambiato,
    None se il cittadino non esiste o se lo username era già quello.
    """
    row = get_citizen_by_telegram_id(conn, telegram_id)
    if row is None:
        return None

    nuovo = normalizza_username(username)
    if row["username"] == nuovo:
        return None

    conn.execute(
        "UPDATE cittadini SET username = ? WHERE telegram_id = ?", (nuovo, telegram_id)
    )
    conn.commit()
    return row, nuovo


# ----------------------------------------------------------------------
# Richieste di cittadinanza
# ----------------------------------------------------------------------

def create_request(
    conn: sqlite3.Connection,
    telegram_id: int,
    username: str | None,
    nome: str,
    cognome: str,
    data_richiesta: str | None = None,
) -> int:
    cursore = conn.execute(
        """
        INSERT INTO richieste (telegram_id, username, nome, cognome, data_richiesta, stato)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            telegram_id,
            normalizza_username(username),
            nome,
            cognome,
            data_richiesta or oggi(),
            STATO_IN_ATTESA,
        ),
    )
    conn.commit()
    return cursore.lastrowid


def get_request(conn: sqlite3.Connection, request_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM richieste WHERE request_id = ?", (request_id,)
    ).fetchone()


def pending_request_for(conn: sqlite3.Connection, telegram_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM richieste WHERE telegram_id = ? AND stato = ?",
        (telegram_id, STATO_IN_ATTESA),
    ).fetchone()


def set_request_notifications(
    conn: sqlite3.Connection, request_id: int, notifiche: list[list[int]]
) -> None:
    conn.execute(
        "UPDATE richieste SET notifiche = ? WHERE request_id = ?",
        (json.dumps(notifiche), request_id),
    )
    conn.commit()


def load_request_notifications(notifiche_json: str | None) -> list[tuple[int, int]]:
    """Rilegge il JSON delle notifiche, tollerando valori corrotti o assenti."""
    if not notifiche_json:
        return []
    try:
        dati = json.loads(notifiche_json)
    except (ValueError, TypeError):
        return []
    coppie = []
    for voce in dati:
        try:
            chat_id, message_id = voce
            coppie.append((int(chat_id), int(message_id)))
        except (TypeError, ValueError):
            continue
    return coppie


def resolve_request(
    conn: sqlite3.Connection,
    request_id: int,
    stato: str,
    admin_id: int,
    admin_username: str | None,
) -> None:
    conn.execute(
        """
        UPDATE richieste
           SET stato = ?, admin_id = ?, admin_username = ?, data_gestione = ?
         WHERE request_id = ?
        """,
        (stato, admin_id, normalizza_username(admin_username), oggi(), request_id),
    )
    conn.commit()
