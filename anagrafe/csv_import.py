"""Import di cittadini da file CSV.

Il parsing è completamente separato dalla scrittura su database, così si può
testare senza toccare né Telegram né SQLite.
"""

from __future__ import annotations

import csv
import io
import sqlite3
from dataclasses import dataclass, field

from . import repository
from .validators import (
    ErroreValidazione,
    normalizza_username,
    valida_nome,
    valida_telegram_id,
)

# Intestazioni riconosciute, normalizzate (minuscole, senza spazi/underscore).
ALIAS_COLONNE = {
    "telegramid": "telegram_id",
    "idtelegram": "telegram_id",
    "id": "telegram_id",
    "userid": "telegram_id",
    "username": "username",
    "utente": "username",
    "nickname": "username",
    "nome": "nome",
    "firstname": "nome",
    "cognome": "cognome",
    "lastname": "cognome",
}

COLONNE_OBBLIGATORIE = ("telegram_id", "nome", "cognome")
ORDINE_POSIZIONALE = ("telegram_id", "username", "nome", "cognome")

DELIMITATORI = [",", ";", "\t"]


@dataclass(frozen=True)
class RigaCSV:
    numero: int
    telegram_id: int
    username: str | None
    nome: str
    cognome: str

    @property
    def nominativo(self) -> str:
        return f"{self.nome} {self.cognome}"


@dataclass(frozen=True)
class RigaScartata:
    numero: int
    motivo: str
    contenuto: str


@dataclass
class Parsing:
    righe: list[RigaCSV] = field(default_factory=list)
    scartate: list[RigaScartata] = field(default_factory=list)
    intestazione_trovata: bool = False


@dataclass
class Esito:
    inseriti: list[tuple[int, RigaCSV]] = field(default_factory=list)
    saltati: list[tuple[int, RigaCSV]] = field(default_factory=list)
    scartate: list[RigaScartata] = field(default_factory=list)

    @property
    def totale_letto(self) -> int:
        return len(self.inseriti) + len(self.saltati) + len(self.scartate)


def decodifica(dati: bytes) -> str:
    """Decodifica il file provando prima UTF-8 (con o senza BOM)."""
    for codifica in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return dati.decode(codifica)
        except UnicodeDecodeError:
            continue
    return dati.decode("utf-8", errors="replace")


def _delimitatore(testo: str) -> str:
    """Indovina il separatore: prima csv.Sniffer, poi un conteggio grezzo."""
    campione = testo[:4096]
    try:
        return csv.Sniffer().sniff(campione, delimiters="".join(DELIMITATORI)).delimiter
    except csv.Error:
        pass
    conteggi = {d: campione.count(d) for d in DELIMITATORI}
    migliore = max(conteggi, key=lambda d: conteggi[d])
    return migliore if conteggi[migliore] else ","


def _normalizza_intestazione(valore: str) -> str:
    return "".join(ch for ch in str(valore).lower() if ch.isalnum())


def _mappa_colonne(riga: list[str]) -> dict[str, int] | None:
    """Se la riga sembra un'intestazione, restituisce colonna -> indice."""
    mappa: dict[str, int] = {}
    for indice, cella in enumerate(riga):
        chiave = ALIAS_COLONNE.get(_normalizza_intestazione(cella))
        if chiave and chiave not in mappa:
            mappa[chiave] = indice
    if all(colonna in mappa for colonna in COLONNE_OBBLIGATORIE):
        return mappa
    return None


def _riga_vuota(riga: list[str]) -> bool:
    return all(not str(cella).strip() for cella in riga)


def _valore(riga: list[str], mappa: dict[str, int], colonna: str) -> str:
    indice = mappa.get(colonna)
    if indice is None or indice >= len(riga):
        return ""
    return riga[indice]


def parse_csv(testo: str) -> Parsing:
    """Legge il CSV e separa le righe valide da quelle da scartare.

    Riconosce l'intestazione per nome di colonna (con alias); se non ne trova
    una, assume l'ordine posizionale telegram_id, username, nome, cognome.
    Le righe completamente vuote vengono ignorate in silenzio: i file esportati
    da fogli di calcolo ne contengono spesso una in cima.
    """
    risultato = Parsing()
    if not testo.strip():
        return risultato

    lettore = csv.reader(io.StringIO(testo), delimiter=_delimitatore(testo))
    mappa: dict[str, int] | None = None
    visti: dict[int, int] = {}  # telegram_id -> numero di riga della prima occorrenza

    for numero, riga in enumerate(lettore, start=1):
        if not riga or _riga_vuota(riga):
            continue

        if mappa is None:
            intestazione = _mappa_colonne(riga)
            if intestazione is not None:
                mappa = intestazione
                risultato.intestazione_trovata = True
                continue
            mappa = {nome: i for i, nome in enumerate(ORDINE_POSIZIONALE)}

        grezzo = ", ".join(str(c).strip() for c in riga)
        try:
            telegram_id = valida_telegram_id(_valore(riga, mappa, "telegram_id"))
            nome = valida_nome(_valore(riga, mappa, "nome"), "Il nome")
            cognome = valida_nome(_valore(riga, mappa, "cognome"), "Il cognome")
            username = normalizza_username(_valore(riga, mappa, "username"))
        except ErroreValidazione as exc:
            risultato.scartate.append(RigaScartata(numero, str(exc), grezzo))
            continue

        if telegram_id in visti:
            risultato.scartate.append(
                RigaScartata(
                    numero,
                    f"ID Telegram duplicato nel file (già alla riga {visti[telegram_id]}).",
                    grezzo,
                )
            )
            continue

        visti[telegram_id] = numero
        risultato.righe.append(
            RigaCSV(
                numero=numero,
                telegram_id=telegram_id,
                username=username,
                nome=nome,
                cognome=cognome,
            )
        )

    return risultato


def importa_righe(conn: sqlite3.Connection, parsing: Parsing) -> Esito:
    """Scrive sul registro le righe valide, saltando i cittadini già presenti."""
    esito = Esito(scartate=list(parsing.scartate))

    for riga in parsing.righe:
        try:
            citizen_id = repository.insert_citizen(
                conn,
                telegram_id=riga.telegram_id,
                username=riga.username,
                nome=riga.nome,
                cognome=riga.cognome,
            )
        except repository.CittadinoGiaEsistente as exc:
            esito.saltati.append((exc.citizen_id, riga))
        else:
            esito.inseriti.append((citizen_id, riga))

    return esito


def importa_da_bytes(conn: sqlite3.Connection, dati: bytes) -> Esito:
    """Scorciatoia: decodifica, analizza e importa in un colpo solo."""
    return importa_righe(conn, parse_csv(decodifica(dati)))


MAX_SCARTATE_MOSTRATE = 15


def render_esito(esito: Esito) -> str:
    """Resoconto leggibile da mandare in chat dopo un import."""
    parti = [
        "📥 Import CSV completato",
        "",
        f"• Inseriti: {len(esito.inseriti)}",
        f"• Saltati (già cittadini): {len(esito.saltati)}",
        f"• Righe non valide: {len(esito.scartate)}",
    ]

    if esito.saltati:
        parti.append("")
        parti.append("Già presenti nel registro:")
        for citizen_id, riga in esito.saltati[:MAX_SCARTATE_MOSTRATE]:
            parti.append(f"  #{citizen_id} — {riga.nominativo} ({riga.telegram_id})")
        rimanenti = len(esito.saltati) - MAX_SCARTATE_MOSTRATE
        if rimanenti > 0:
            parti.append(f"  …e altri {rimanenti}.")

    if esito.scartate:
        parti.append("")
        parti.append("Righe non valide:")
        for scartata in esito.scartate[:MAX_SCARTATE_MOSTRATE]:
            parti.append(f"  riga {scartata.numero}: {scartata.motivo}")
        rimanenti = len(esito.scartate) - MAX_SCARTATE_MOSTRATE
        if rimanenti > 0:
            parti.append(f"  …e altre {rimanenti}.")

    if not esito.totale_letto:
        parti.append("")
        parti.append("⚠️ Il file non conteneva nessuna riga leggibile.")

    return "\n".join(parti)
