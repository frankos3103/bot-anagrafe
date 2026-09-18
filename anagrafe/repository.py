"""Tutte le query sul registro. Nessuna dipendenza da Telegram: si testa da sola."""

from __future__ import annotations

import json
import re
import sqlite3
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from difflib import SequenceMatcher

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


def get_citizens_by_username(conn: sqlite3.Connection, username: str) -> list[sqlite3.Row]:
    """Tutti i cittadini con quel tag (più di uno solo in dati vecchi e incoerenti)."""
    return conn.execute(
        "SELECT * FROM cittadini WHERE username = ? COLLATE NOCASE ORDER BY citizen_id",
        (normalizza_username(username),),
    ).fetchall()


# ----------------------------------------------------------------------
# Ricerca
# ----------------------------------------------------------------------

SOGLIA_SOMIGLIANZA = 0.75
LUNGHEZZA_MIN_FUZZY = 3


def normalizza_testo(valore: object) -> str:
    """Minuscolo e senza accenti: «Nicolò» e «nicolo» diventano uguali."""
    if valore is None:
        return ""
    scomposto = unicodedata.normalize("NFKD", str(valore))
    return "".join(c for c in scomposto if not unicodedata.combining(c)).casefold()


def _token(query: str) -> list[str]:
    return [t for t in re.split(r"[\s,]+", query.strip()) if t]


def _parole(row: sqlite3.Row) -> list[str]:
    """Le parole di nome, cognome e username, normalizzate."""
    testo = f"{row['nome']} {row['cognome']} {row['username'] or ''}"
    return normalizza_testo(testo).replace("_", " ").split()


def _punteggio_token(token: str, row: sqlite3.Row) -> int:
    """0 se il token non compare; altrimenti più alto quanto più è preciso."""
    if token.startswith("#"):
        numero = token[1:]
        return 3 if numero.isdigit() and int(numero) == row["citizen_id"] else 0

    if token.startswith("@"):
        cercato = normalizza_testo(token[1:])
        username = normalizza_testo(row["username"])
        if not cercato or not username:
            return 0
        if username == cercato:
            return 3
        return 1 if cercato in username else 0

    cercato = normalizza_testo(token)
    punteggio = 0
    if cercato.isdigit():
        if int(cercato) == row["citizen_id"]:
            punteggio = 2
        if cercato in str(row["telegram_id"]):
            punteggio = max(punteggio, 3 if cercato == str(row["telegram_id"]) else 1)

    campi = [normalizza_testo(row[c]) for c in ("nome", "cognome", "username")]
    if any(cercato in campo for campo in campi):
        punteggio = max(punteggio, 1)
    parole = _parole(row)
    if cercato in parole:
        punteggio = max(punteggio, 3)
    elif any(parola.startswith(cercato) for parola in parole):
        punteggio = max(punteggio, 2)
    return punteggio


def search_citizens(conn: sqlite3.Connection, query: str) -> list[sqlite3.Row]:
    """Ogni parola della query deve comparire in almeno un campo.

    «Mario Rossi», «rossi mario», «@mariorossi», «#3» e l'ID Telegram trovano
    tutti lo stesso cittadino. Maiuscole e accenti sono ignorati. I risultati
    più precisi (nome e cognome esatti, parola intera, inizio di parola)
    vengono prima.
    """
    token = _token(query)
    if not token:
        return []
    frase = normalizza_testo(" ".join(token))

    trovati: list[tuple[int, int, sqlite3.Row]] = []
    for row in list_citizens(conn):
        punteggi = [_punteggio_token(t, row) for t in token]
        if not all(punteggi):
            continue
        nome = normalizza_testo(row["nome"])
        cognome = normalizza_testo(row["cognome"])
        esatto = frase in (f"{nome} {cognome}", f"{cognome} {nome}")
        totale = sum(punteggi) + (100 if esatto else 0)
        trovati.append((-totale, row["citizen_id"], row))

    trovati.sort(key=lambda t: t[:2])
    return [row for _, _, row in trovati]


def suggest_citizens(
    conn: sqlite3.Connection, query: str, limite: int = 5
) -> list[sqlite3.Row]:
    """Ricerca tollerante ai refusi, da usare quando search_citizens è vuota."""
    token = [
        normalizza_testo(t.lstrip("@#"))
        for t in _token(query)
        if len(t.lstrip("@#")) >= LUNGHEZZA_MIN_FUZZY
    ]
    if not token:
        return []

    candidati: list[tuple[float, int, sqlite3.Row]] = []
    for row in list_citizens(conn):
        parole = _parole(row)
        if row["username"]:
            parole.append(normalizza_testo(row["username"]))
        if not parole:
            continue
        migliori = [
            max(SequenceMatcher(None, t, p).ratio() for p in parole) for t in token
        ]
        if min(migliori) >= SOGLIA_SOMIGLIANZA:
            candidati.append((-sum(migliori) / len(migliori), row["citizen_id"], row))

    candidati.sort(key=lambda c: c[:2])
    return [row for _, _, row in candidati[:limite]]


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


@dataclass
class CambioUsername:
    """Esito di update_username.

    `riga` è il cittadino prima del cambio (None se chi ha scritto non è
    cittadino); `sottratto_a` sono i cittadini che avevano quel tag in modo
    ormai obsoleto e ne sono stati privati.
    """

    riga: sqlite3.Row | None
    nuovo: str | None
    sottratto_a: list[sqlite3.Row] = field(default_factory=list)


def update_username(
    conn: sqlite3.Connection, telegram_id: int, username: str | None
) -> CambioUsername | None:
    """Registra il tag attuale di un utente Telegram.

    Aggiorna lo username del cittadino con quel telegram_id, se esiste. Poiché
    un tag Telegram appartiene a un solo utente alla volta, chi lo usa adesso
    ne è il titolare: lo si toglie a qualunque altro cittadino lo avesse
    ancora registrato. Restituisce None se non è cambiato nulla.
    """
    nuovo = normalizza_username(username)
    row = get_citizen_by_telegram_id(conn, telegram_id)

    sottratto_a: list[sqlite3.Row] = []
    if nuovo is not None:
        sottratto_a = [
            r for r in get_citizens_by_username(conn, nuovo) if r["telegram_id"] != telegram_id
        ]
        for r in sottratto_a:
            conn.execute(
                "UPDATE cittadini SET username = NULL WHERE citizen_id = ?",
                (r["citizen_id"],),
            )

    cambiato = row is not None and row["username"] != nuovo
    if cambiato:
        conn.execute(
            "UPDATE cittadini SET username = ? WHERE telegram_id = ?", (nuovo, telegram_id)
        )

    if not cambiato and not sottratto_a:
        return None
    conn.commit()
    return CambioUsername(riga=row if cambiato else None, nuovo=nuovo, sottratto_a=sottratto_a)


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
