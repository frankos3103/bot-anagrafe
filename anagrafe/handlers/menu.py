"""La pulsantiera /menu: esegue ogni comando senza doverne ricordare la sintassi.

I comandi senza parametri partono subito; quelli con parametri aprono un
wizard che chiede un valore alla volta e conclude con un riepilogo da
confermare. I pulsanti e i campi sono letti dal registro in anagrafe.commands,
quindi un comando nuovo compare qui senza toccare questo file.
"""

from __future__ import annotations

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from ..commands import Campo, Comando, comandi_per_ruolo, trova_comando
from ..validators import ErroreValidazione
from .azioni import AZIONI
from .common import rispondi, ruolo_utente
from .importazione import ATTESA_CSV, ISTRUZIONI

logger = logging.getLogger(__name__)

SCELTA, RACCOLTA, CONFERMA = range(3)

DURATA_MASSIMA = 300  # secondi di inattività prima che il wizard scada

TESTO_MENU = (
    "⌨️ Pulsantiera comandi\n\n"
    "Scegli un'azione: quelle che richiedono dei dati te li chiederanno "
    "un passo alla volta."
)

BOTTONE_ANNULLA = InlineKeyboardButton("❌ Annulla", callback_data="menu:annulla")
BOTTONE_SALTA = InlineKeyboardButton("⏭ Salta", callback_data="menu:salta")


# ----------------------------------------------------------------------
# Costruzione della tastiera
# ----------------------------------------------------------------------

def tastiera_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> InlineKeyboardMarkup:
    """Un pulsante per ogni comando permesso al ruolo di chi guarda."""
    comandi = comandi_per_ruolo(ruolo_utente(update, context), solo_menu=True)
    bottoni = [
        InlineKeyboardButton(c.label, callback_data=f"menu:cmd:{c.nome}") for c in comandi
    ]
    righe = [bottoni[i : i + 2] for i in range(0, len(bottoni), 2)]
    righe.append([InlineKeyboardButton("✖️ Chiudi", callback_data="menu:chiudi")])
    return InlineKeyboardMarkup(righe)


async def _mostra_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await rispondi(update, TESTO_MENU, reply_markup=tastiera_menu(update, context))
    return SCELTA


async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("wizard", None)
    return await _mostra_menu(update, context)


# ----------------------------------------------------------------------
# Wizard
# ----------------------------------------------------------------------

def _wizard(context: ContextTypes.DEFAULT_TYPE) -> dict | None:
    return context.user_data.get("wizard")


def _campo_corrente(context: ContextTypes.DEFAULT_TYPE) -> tuple[Comando, Campo] | None:
    stato = _wizard(context)
    if not stato:
        return None
    comando = trova_comando(stato["comando"])
    if comando is None or stato["indice"] >= len(comando.campi):
        return None
    return comando, comando.campi[stato["indice"]]


async def _chiedi_campo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Invia il prompt del campo corrente, o passa al riepilogo se sono finiti."""
    corrente = _campo_corrente(context)
    if corrente is None:
        return await _mostra_riepilogo(update, context)

    comando, campo = corrente
    passo = f"Passo {_wizard(context)['indice'] + 1} di {len(comando.campi)}"
    testo = f"{comando.emoji} {comando.nome}\n{passo}\n\n{campo.prompt}"
    if campo.opzionale:
        testo += "\n\n(facoltativo: premi «Salta» per lasciarlo vuoto)"

    bottoni = [BOTTONE_SALTA, BOTTONE_ANNULLA] if campo.opzionale else [BOTTONE_ANNULLA]
    await rispondi(update, testo, reply_markup=InlineKeyboardMarkup([bottoni]))
    return RACCOLTA


def _descrizione_valore(valore) -> str:
    return "(nessuno)" if valore in (None, "") else str(valore)


async def _mostra_riepilogo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    stato = _wizard(context)
    comando = trova_comando(stato["comando"])
    righe = [f"{comando.emoji} Conferma «{comando.nome}»", ""]
    for campo in comando.campi:
        righe.append(
            f"• {campo.etichetta}: {_descrizione_valore(stato['valori'].get(campo.chiave))}"
        )

    tastiera = InlineKeyboardMarkup(
        [[InlineKeyboardButton("✅ Conferma", callback_data="menu:conferma"), BOTTONE_ANNULLA]]
    )
    await rispondi(update, "\n".join(righe), reply_markup=tastiera)
    return CONFERMA


async def on_valore(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Riceve la risposta dell'utente a un prompt del wizard."""
    corrente = _campo_corrente(context)
    if corrente is None:
        return await cmd_menu(update, context)

    _, campo = corrente
    try:
        valore = campo.validatore(update.effective_message.text or "")
    except ErroreValidazione as exc:
        await rispondi(update, f"⚠️ {exc}\nRiprova.")
        return await _chiedi_campo(update, context)

    stato = _wizard(context)
    stato["valori"][campo.chiave] = valore
    stato["indice"] += 1
    return await _chiedi_campo(update, context)


async def on_salta(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    corrente = _campo_corrente(context)
    if corrente is None:
        return await cmd_menu(update, context)

    _, campo = corrente
    stato = _wizard(context)
    stato["valori"][campo.chiave] = None
    stato["indice"] += 1
    return await _chiedi_campo(update, context)


# ----------------------------------------------------------------------
# Router dei pulsanti
# ----------------------------------------------------------------------

async def on_scelta_comando(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    nome = query.data.split(":", 2)[2]
    comando = trova_comando(nome)

    if comando is None:
        await query.answer("Comando non riconosciuto.", show_alert=True)
        return SCELTA

    # I permessi si ricontrollano al click: la tastiera potrebbe essere vecchia.
    if ruolo_utente(update, context) < comando.ruolo:
        await query.answer("⛔ Non sei autorizzato a usare questo comando.", show_alert=True)
        return SCELTA

    await query.answer()

    if comando.nome == "importa":
        # L'import ha bisogno di un allegato: usciamo dal wizard e aspettiamo il file.
        context.user_data[ATTESA_CSV] = True
        await rispondi(update, ISTRUZIONI)
        return ConversationHandler.END

    if not comando.richiede_input:
        await AZIONI[comando.nome](update, context, {})
        return await _mostra_menu(update, context)

    context.user_data["wizard"] = {"comando": comando.nome, "valori": {}, "indice": 0}
    return await _chiedi_campo(update, context)


async def on_conferma(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    stato = context.user_data.pop("wizard", None)
    if not stato:
        return await cmd_menu(update, context)

    comando = trova_comando(stato["comando"])
    if comando is None or ruolo_utente(update, context) < comando.ruolo:
        await rispondi(update, "⛔ Non sei autorizzato a usare questo comando.")
        return await _mostra_menu(update, context)

    mancanti = [
        campo.etichetta
        for campo in comando.campi
        if campo.chiave not in stato["valori"] and not campo.opzionale
    ]
    if mancanti:
        # Non dovrebbe accadere: si arriva qui solo dopo il riepilogo.
        await rispondi(
            update,
            "⚠️ Mancano dei dati (" + ", ".join(mancanti) + "). Ricominciamo.",
        )
        return await _mostra_menu(update, context)

    await AZIONI[comando.nome](update, context, stato["valori"])
    return await _mostra_menu(update, context)


async def on_annulla(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("wizard", None)
    context.user_data.pop(ATTESA_CSV, None)
    if update.callback_query:
        await update.callback_query.answer("Annullato.")
    await rispondi(update, "Operazione annullata.")
    return await _mostra_menu(update, context)


async def on_chiudi(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("wizard", None)
    await update.callback_query.answer()
    await update.callback_query.edit_message_text("Pulsantiera chiusa. Riaprila con /menu.")
    return ConversationHandler.END


async def on_timeout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("wizard", None)
    await rispondi(update, "⌛ Pulsantiera scaduta per inattività. Riaprila con /menu.")
    return ConversationHandler.END


def build_menu_handler() -> ConversationHandler:
    scelta_handlers = [
        CallbackQueryHandler(on_scelta_comando, pattern=r"^menu:cmd:"),
        CallbackQueryHandler(on_chiudi, pattern=r"^menu:chiudi$"),
    ]
    return ConversationHandler(
        entry_points=[CommandHandler("menu", cmd_menu)] + scelta_handlers,
        states={
            SCELTA: scelta_handlers,
            RACCOLTA: [
                CallbackQueryHandler(on_salta, pattern=r"^menu:salta$"),
                CallbackQueryHandler(on_annulla, pattern=r"^menu:annulla$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, on_valore),
            ],
            CONFERMA: [
                CallbackQueryHandler(on_conferma, pattern=r"^menu:conferma$"),
                CallbackQueryHandler(on_annulla, pattern=r"^menu:annulla$"),
            ],
            ConversationHandler.TIMEOUT: [
                MessageHandler(filters.ALL, on_timeout),
                CallbackQueryHandler(on_timeout),
            ],
        },
        fallbacks=[
            CommandHandler("annulla", on_annulla),
            CallbackQueryHandler(on_annulla, pattern=r"^menu:annulla$"),
        ],
        conversation_timeout=DURATA_MASSIMA,
        name="menu",
    )
