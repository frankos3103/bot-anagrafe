"""Produzione dei file di export: Markdown da leggere, CSV da reimportare.

I due formati hanno scopi diversi. Il Markdown è una tabella da guardare; il
CSV è un file di scambio, e le sue intestazioni sono **le stesse che
csv_import riconosce**: un registro esportato in CSV si può reimportare senza
ritoccarlo. È l'invariante che tiene insieme export e import, e un test la
verifica facendo il giro completo.

Nessuna dipendenza da Telegram: qui si producono solo byte e nomi di file.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

from .commands import FORMATO_CSV, FORMATO_MD, etichetta_tipologia
from .formatting import cognome_elenco, escape_tabella

# Excel apre un CSV UTF-8 come se fosse ANSI, e i nomi accentati escono
# illeggibili: il BOM glielo fa riconoscere. decodifica() lo togli in lettura.
CODIFICA_CSV = "utf-8-sig"
FINE_RIGA_CSV = "\r\n"


@dataclass(frozen=True)
class Documento:
    """Un file pronto da allegare in chat."""

    contenuto: bytes
    nome_file: str


# ----------------------------------------------------------------------
# Intestazioni: una sola definizione per il Markdown e per il CSV
# ----------------------------------------------------------------------

COLONNE_CITTADINI = (
    "ID cittadino",
    "ID Telegram",
    "Username",
    "Nome",
    "Cognome",
)

COLONNE_ATTIVITA = (
    "ID attività",
    "Nome",
    "Tipologia",
    "Descrizione",
    "Contatto",
    "Proprietario",
)


def _celle_cittadino(row: Mapping, per_lettura: bool) -> list[str]:
    """Le celle di un cittadino.

    Nel Markdown il cognome va in maiuscolo, come in tutti gli elenchi del
    progetto; nel CSV resta come è scritto nel registro, perché quel file serve
    a rientrare dall'import e non deve alterare i dati.
    """
    username = f"@{row['username']}" if row["username"] else ""
    cognome = cognome_elenco(row["cognome"]) if per_lettura else str(row["cognome"])
    return [
        str(row["citizen_id"]),
        str(row["telegram_id"]),
        username,
        str(row["nome"]),
        cognome,
    ]


def _celle_attivita(row: Mapping) -> list[str]:
    return [
        str(row["attivita_id"]),
        str(row["nome_attivita"]),
        etichetta_tipologia(row["tipologia"]),
        str(row["descrizione"]),
        str(row["contatto_link"] or ""),
        str(row["owner_id"]),
    ]


# ----------------------------------------------------------------------
# Markdown
# ----------------------------------------------------------------------

def _tabella(
    titolo: str,
    etichetta_totale: str,
    colonne: Sequence[str],
    righe: Iterable[Sequence[str]],
    totale: int,
) -> str:
    """Un documento Markdown con una tabella.

    Le celle passano da escape_tabella: una pipe o un capoverso dentro a un
    nome spezzerebbero la tabella.
    """
    linee = [
        f"# {titolo}",
        "",
        f"{etichetta_totale}: {totale}",
        "",
        "| " + " | ".join(colonne) + " |",
        "|" + "---|" * len(colonne),
    ]
    for celle in righe:
        linee.append("| " + " | ".join(escape_tabella(c) for c in celle) + " |")
    return "\n".join(linee) + "\n"


def tabella_markdown(righe: Iterable[Mapping], totale: int) -> str:
    """Documento Markdown del registro dei cittadini."""
    return _tabella(
        "Registro Cittadini",
        "Totale cittadini",
        COLONNE_CITTADINI,
        (_celle_cittadino(r, per_lettura=True) for r in righe),
        totale,
    )


def tabella_markdown_attivita(righe: Iterable[Mapping], totale: int) -> str:
    """Documento Markdown del Registro Pubblico delle Attività."""
    return _tabella(
        "Registro Pubblico delle Attività",
        "Totale attività",
        COLONNE_ATTIVITA,
        (_celle_attivita(r) for r in righe),
        totale,
    )


# ----------------------------------------------------------------------
# CSV
# ----------------------------------------------------------------------

def _csv(colonne: Sequence[str], righe: Iterable[Sequence[str]]) -> bytes:
    buffer = io.StringIO(newline="")
    scrittore = csv.writer(buffer, lineterminator=FINE_RIGA_CSV)
    scrittore.writerow(colonne)
    scrittore.writerows(righe)
    return buffer.getvalue().encode(CODIFICA_CSV)


# ----------------------------------------------------------------------
# Confezionamento
# ----------------------------------------------------------------------

def esporta_cittadini(righe: Sequence[Mapping], formato: str) -> Documento:
    if formato == FORMATO_CSV:
        return Documento(
            _csv(COLONNE_CITTADINI, (_celle_cittadino(r, per_lettura=False) for r in righe)),
            "registro_cittadini.csv",
        )
    return Documento(
        tabella_markdown(righe, len(righe)).encode("utf-8"),
        "registro_cittadini.md",
    )


def esporta_attivita(righe: Sequence[Mapping], formato: str) -> Documento:
    if formato == FORMATO_CSV:
        return Documento(
            _csv(COLONNE_ATTIVITA, (_celle_attivita(r) for r in righe)),
            "registro_attivita.csv",
        )
    return Documento(
        tabella_markdown_attivita(righe, len(righe)).encode("utf-8"),
        "registro_attivita.md",
    )


# Il formato predefinito quando non viene chiesto (comando testuale senza
# argomenti): è quello che /esporta_cittadini produceva prima dei due formati.
FORMATO_PREDEFINITO = FORMATO_MD
