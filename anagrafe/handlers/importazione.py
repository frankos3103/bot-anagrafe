"""Import dei registri da un file CSV allegato in chat.

Due registri si importano allo stesso modo — l'utente manda un file, il bot lo
scarica e lo passa al parser — ma con colonne e regole diverse. Le differenze
stanno tutte nella tabella IMPORTAZIONI, così il flusso dell'allegato è scritto
una volta sola e aggiungere un terzo registro non lo tocca.
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from typing import Callable

from telegram import Update
from telegram.ext import ContextTypes

from .. import csv_attivita, csv_import
from ..commands import render_uso, trova_comando
from ..logbook import fmt_utente, send_log
from ..roles import Role
from .common import db, richiede, rispondi, ruolo_utente

logger = logging.getLogger(__name__)

# Chiave in user_data: il menu la imposta col nome del comando di import, per
# dire «il prossimo file è un import, e di questo registro».
ATTESA_CSV = "attesa_csv"

DIMENSIONE_MASSIMA = 2 * 1024 * 1024  # 2 MB


ISTRUZIONI_CITTADINI = (
    "📥 Import cittadini da CSV\n\n"
    "Invia un file .csv allegandolo a questa chat con didascalia "
    "/importa_cittadini.\n\n"
    "Colonne attese (l'intestazione può usare nomi equivalenti):\n"
    "  ID Telegram, Username, Nome, Cognome\n\n"
    "Esempio:\n"
    "  ID Telegram,Username,Nome,Cognome\n"
    "  123456789,@mariorossi,Mario,Rossi\n\n"
    "• Se il file non ha intestazione, le colonne sono lette in quell'ordine.\n"
    "• I cittadini già registrati vengono saltati, non duplicati.\n"
    "• Le righe non valide vengono elencate nel resoconto finale.\n"
    "• Il file prodotto da /esporta_cittadini in formato CSV si reimporta così "
    "com'è."
)

ISTRUZIONI_ATTIVITA = (
    "📥 Import attività da CSV\n\n"
    "Invia un file .csv allegandolo a questa chat con didascalia "
    "/importa_attivita.\n\n"
    "Colonne attese (l'intestazione può usare nomi equivalenti):\n"
    "  Nome, Tipologia, Descrizione, Contatto, Proprietario\n\n"
    "Esempio:\n"
    "  Nome,Tipologia,Descrizione,Contatto,Proprietario\n"
    "  Pizzeria Da Mario,Attività Privata,Pizza al taglio,@pizzeria,123456789\n\n"
    "• La tipologia è Organizzazione, Associazione o Attività Privata.\n"
    "• Il proprietario si indica con l'ID Telegram, con #ID cittadino oppure "
    "con @username, e **deve essere un cittadino iscritto**.\n"
    "• Il contatto è facoltativo.\n"
    "• Un proprietario non può avere due attività attive con lo stesso nome.\n"
    "• Le attività importate non vengono pubblicate sulla Gazzetta Ciompista.\n"
    "• Il file prodotto da /esporta_attivita in formato CSV si reimporta così "
    "com'è."
)


@dataclass(frozen=True)
class Importazione:
    """Tutto ciò che distingue l'import di un registro dall'altro."""

    comando: str
    etichetta: str
    istruzioni: str
    importa: Callable[[sqlite3.Connection, bytes], object]
    render: Callable[[object], str]
    riuscite: Callable[[object], int]
    riassunto: Callable[[object], str]


IMPORTAZIONI: dict[str, Importazione] = {
    "importa_cittadini": Importazione(
        comando="importa_cittadini",
        etichetta="cittadini",
        istruzioni=ISTRUZIONI_CITTADINI,
        importa=csv_import.importa_da_bytes,
        render=csv_import.render_esito,
        riuscite=lambda e: len(e.inseriti),
        riassunto=lambda e: (
            f"Inseriti: {len(e.inseriti)} — saltati: {len(e.saltati)} — "
            f"non validi: {len(e.scartate)}"
        ),
    ),
    "importa_attivita": Importazione(
        comando="importa_attivita",
        etichetta="attività",
        istruzioni=ISTRUZIONI_ATTIVITA,
        importa=csv_attivita.importa_da_bytes,
        render=csv_attivita.render_esito,
        riuscite=lambda e: len(e.iscritte),
        riassunto=lambda e: (
            f"Iscritte: {len(e.iscritte)} — saltate: {len(e.saltate)} — "
            f"non valide: {len(e.scartate)}"
        ),
    ),
}


def istruzioni(nome_comando: str) -> str:
    """Il testo che spiega come si fa quell'import. Lo usa anche il wizard."""
    voce = IMPORTAZIONI.get(nome_comando)
    return voce.istruzioni if voce is not None else ""


async def _chiedi_file(
    update: Update, context: ContextTypes.DEFAULT_TYPE, voce: Importazione
) -> None:
    context.user_data[ATTESA_CSV] = voce.comando
    await rispondi(update, voce.istruzioni)


@richiede(Role.ADMIN)
async def cmd_importa_cittadini(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Spiega come si fa e si mette in attesa del file."""
    await _chiedi_file(update, context, IMPORTAZIONI["importa_cittadini"])


@richiede(Role.ADMIN)
async def cmd_importa_attivita(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Spiega come si fa e si mette in attesa del file."""
    await _chiedi_file(update, context, IMPORTAZIONI["importa_attivita"])


def _quale_import(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> Importazione | None:
    """Di quale registro è questo documento? None se non è un import.

    Lo dice la didascalia, oppure l'attesa impostata da chi ha appena chiesto
    di importare (dal comando o dalla pulsantiera).
    """
    didascalia = (update.effective_message.caption or "").strip().lower()
    for voce in IMPORTAZIONI.values():
        if didascalia.startswith(f"/{voce.comando}"):
            return voce

    # Senza utente (es. post di un canale) user_data è None.
    atteso = context.user_data.get(ATTESA_CSV) if context.user_data else None
    return IMPORTAZIONI.get(atteso) if atteso else None


async def on_documento(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Riceve un allegato e, se è un import richiesto, lo elabora."""
    messaggio = update.effective_message
    if messaggio is None or messaggio.document is None:
        return

    voce = _quale_import(update, context)
    if voce is None:
        return

    if context.user_data is not None:
        context.user_data.pop(ATTESA_CSV, None)

    if ruolo_utente(update, context) < Role.ADMIN:
        await rispondi(update, "⛔ Solo un amministratore può importare il registro.")
        return

    documento = messaggio.document
    nome_file = (documento.file_name or "").lower()

    if not nome_file.endswith(".csv"):
        await rispondi(
            update,
            "⚠️ Serve un file con estensione .csv "
            f"(ricevuto «{documento.file_name}»).\n\n"
            f"{render_uso(trova_comando(voce.comando))}",
        )
        return

    if documento.file_size and documento.file_size > DIMENSIONE_MASSIMA:
        await rispondi(
            update,
            "⚠️ Il file è troppo grande (limite: "
            f"{DIMENSIONE_MASSIMA // (1024 * 1024)} MB).",
        )
        return

    await rispondi(update, "⏳ Sto leggendo il file…")

    try:
        file_telegram = await documento.get_file()
        dati = bytes(await file_telegram.download_as_bytearray())
    except Exception as exc:  # noqa: BLE001 - qualunque errore va riportato all'admin
        logger.exception("Errore scaricando il CSV")
        await rispondi(update, f"⚠️ Non sono riuscito a scaricare il file: {exc}")
        return

    with db(context) as conn:
        esito = voce.importa(conn, dati)

    await rispondi(update, voce.render(esito))

    if voce.riuscite(esito):
        await send_log(
            context,
            f"📥 *Import CSV* — {voce.etichetta}\n"
            f"Da: {fmt_utente(update.effective_user)}\n"
            f"File: {documento.file_name}\n"
            f"{voce.riassunto(esito)}",
        )
