"""Import del registro da un file CSV allegato in chat."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from ..commands import render_uso, trova_comando
from ..csv_import import importa_da_bytes, render_esito
from ..logbook import fmt_utente, send_log
from ..roles import Role
from .common import db, richiede, rispondi, ruolo_utente

logger = logging.getLogger(__name__)

# Chiave in user_data: il menu la imposta per dire «il prossimo file è un import».
ATTESA_CSV = "attesa_csv"

DIMENSIONE_MASSIMA = 2 * 1024 * 1024  # 2 MB

ISTRUZIONI = (
    "📥 Import cittadini da CSV\n\n"
    "Invia un file .csv allegandolo a questa chat con didascalia /importa.\n\n"
    "Colonne attese (l'intestazione può usare nomi equivalenti):\n"
    "  Telegram ID, Username, Nome, Cognome\n\n"
    "Esempio:\n"
    "  Telegram ID,Username,Nome,Cognome\n"
    "  123456789,@mariorossi,Mario,Rossi\n\n"
    "• Se il file non ha intestazione, le colonne sono lette in quell'ordine.\n"
    "• I cittadini già registrati vengono saltati, non duplicati.\n"
    "• Le righe non valide vengono elencate nel resoconto finale."
)


@richiede(Role.ADMIN)
async def cmd_importa(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/importa senza allegato: spiega come si fa e si mette in attesa del file."""
    context.user_data[ATTESA_CSV] = True
    await rispondi(update, ISTRUZIONI)


def _e_un_import(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Questo documento è destinato a noi?

    Lo è se la didascalia è /importa oppure se l'utente ha appena chiesto di
    importare (da /importa o dalla pulsantiera).
    """
    didascalia = (update.effective_message.caption or "").strip().lower()
    if didascalia.startswith("/importa"):
        return True
    # Senza utente (es. post di un canale) user_data è None.
    return bool(context.user_data and context.user_data.get(ATTESA_CSV))


async def on_documento(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Riceve un allegato e, se è un import richiesto, lo elabora."""
    messaggio = update.effective_message
    if messaggio is None or messaggio.document is None:
        return
    if not _e_un_import(update, context):
        return

    context.user_data.pop(ATTESA_CSV, None)

    if ruolo_utente(update, context) < Role.ADMIN:
        await rispondi(update, "⛔ Solo un amministratore può importare il registro.")
        return

    documento = messaggio.document
    nome_file = (documento.file_name or "").lower()

    if not nome_file.endswith(".csv"):
        comando = trova_comando("importa")
        await rispondi(
            update,
            "⚠️ Serve un file con estensione .csv "
            f"(ricevuto «{documento.file_name}»).\n\n{render_uso(comando)}",
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
        esito = importa_da_bytes(conn, dati)

    await rispondi(update, render_esito(esito))

    if esito.inseriti:
        await send_log(
            context,
            f"📥 *Import CSV*\n"
            f"Da: {fmt_utente(update.effective_user)}\n"
            f"File: {documento.file_name}\n"
            f"Inseriti: {len(esito.inseriti)} — saltati: {len(esito.saltati)} — "
            f"non validi: {len(esito.scartate)}",
        )
