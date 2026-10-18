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

from ..commands import COMMANDS, Campo, Comando, comandi_per_ruolo, trova_comando
from ..validators import ErroreValidazione
from .azioni import AZIONI
from .common import argomenti, rispondi, ruolo_utente
from .controlli import PRECONDIZIONI, VERIFICHE_CAMPO
from .importazione import ATTESA_CSV, ISTRUZIONI

logger = logging.getLogger(__name__)

SCELTA, RACCOLTA, CONFERMA = range(3)

DURATA_MASSIMA = 300  # secondi di inattività prima che il wizard scada

TESTO_MENU = (
    "⌨️ Pulsantiera comandi\n\n"
    "Scegli un'azione: quelle che richiedono dei dati te li chiederanno "
    "un passo alla volta."
)

NEGATO = "⛔ Non sei autorizzato a usare questo comando."

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


async def _termina(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return ConversationHandler.END


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


def _tastiera_campo(stato: dict, campo: Campo) -> InlineKeyboardMarkup:
    """I pulsanti delle opzioni, se il campo le offre, più Salta/Annulla.

    Il callback_data porta gli indici e non le etichette: «menu:opt:1:2» sono
    undici byte, quindi il limite di 64 byte diventa impossibile da superare e
    nessun carattere scritto dall'utente finisce nel callback_data. Il primo
    indice è quello del campo, e serve a riconoscere una tastiera vecchia.
    """
    righe: list[list[InlineKeyboardButton]] = []

    if campo.a_pulsanti:
        bottoni = [
            InlineKeyboardButton(
                opzione.label, callback_data=f"menu:opt:{stato['indice']}:{i}"
            )
            for i, opzione in enumerate(campo.opzioni)
        ]
        passo = max(1, campo.per_riga)
        righe = [bottoni[i : i + passo] for i in range(0, len(bottoni), passo)]

    righe.append([BOTTONE_SALTA, BOTTONE_ANNULLA] if campo.opzionale else [BOTTONE_ANNULLA])
    return InlineKeyboardMarkup(righe)


async def _chiedi_campo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Invia il prompt del campo corrente, o passa al riepilogo se sono finiti."""
    corrente = _campo_corrente(context)
    if corrente is None:
        return await _mostra_riepilogo(update, context)

    comando, campo = corrente
    stato = _wizard(context)
    passo = f"Passo {stato['indice'] + 1} di {len(comando.campi)}"
    testo = f"{comando.emoji} {comando.nome}\n{passo}\n\n{campo.prompt}"
    if campo.a_pulsanti:
        testo += "\n\n(scegli con i pulsanti, oppure scrivi la risposta)"
    if campo.opzionale:
        testo += "\n\n(facoltativo: premi «Salta» per lasciarlo vuoto)"

    await rispondi(update, testo, reply_markup=_tastiera_campo(stato, campo))
    return RACCOLTA


async def _mostra_riepilogo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    stato = _wizard(context)
    comando = trova_comando(stato["comando"])
    righe = [f"{comando.emoji} Conferma «{comando.nome}»", ""]
    for campo in comando.campi:
        righe.append(
            f"• {campo.etichetta}: {campo.mostra(stato['valori'].get(campo.chiave))}"
        )

    tastiera = InlineKeyboardMarkup(
        [[InlineKeyboardButton("✅ Conferma", callback_data="menu:conferma"), BOTTONE_ANNULLA]]
    )
    await rispondi(update, "\n".join(righe), reply_markup=tastiera)
    return CONFERMA


async def _registra_valore(
    update: Update, context: ContextTypes.DEFAULT_TYPE, grezzo: str
) -> int:
    """Valida il valore del campo corrente, lo salva e avanza di un passo.

    È il percorso unico del testo e dei pulsanti: anche una scelta fatta a
    pulsante passa dal validatore del campo e dalle VERIFICHE_CAMPO, così il
    valore salvato è sempre nella forma canonica.
    """
    corrente = _campo_corrente(context)
    if corrente is None:
        return await cmd_menu(update, context)

    comando, campo = corrente
    verifica = VERIFICHE_CAMPO.get((comando.nome, campo.chiave))
    try:
        valore = campo.validatore(grezzo)
        if verifica is not None:
            # Controlla subito sul registro: meglio scoprire ora che l'ID non
            # esiste che dopo aver compilato tutto il resto.
            valore = await verifica(update, context, valore)
    except ErroreValidazione as exc:
        await rispondi(update, f"⚠️ {exc}\nRiprova.")
        return await _chiedi_campo(update, context)

    stato = _wizard(context)
    stato["valori"][campo.chiave] = valore
    stato["indice"] += 1
    return await _chiedi_campo(update, context)


async def on_valore(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Riceve la risposta scritta dell'utente a un prompt del wizard."""
    return await _registra_valore(update, context, update.effective_message.text or "")


async def on_opzione(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Click su un pulsante-opzione: «menu:opt:<indice_campo>:<indice_opzione>»."""
    query = update.callback_query
    corrente = _campo_corrente(context)
    if corrente is None:
        await query.answer()
        return await cmd_menu(update, context)

    _, campo = corrente
    try:
        _, _, indice_campo, indice_opzione = query.data.split(":")
        indice_campo, indice_opzione = int(indice_campo), int(indice_opzione)
    except ValueError:
        await query.answer("Scelta non riconosciuta.", show_alert=True)
        return RACCOLTA

    # Una tastiera vecchia (un passo già superato, o un wizard precedente ancora
    # in cronologia) non deve poter scrivere nel campo sbagliato.
    if indice_campo != _wizard(context)["indice"] or indice_opzione >= len(campo.opzioni):
        await query.answer("Questo pulsante non è più valido.", show_alert=True)
        return await _chiedi_campo(update, context)

    opzione = campo.opzioni[indice_opzione]
    await query.answer(opzione.label)
    return await _registra_valore(update, context, opzione.chiave)


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
# Avvio di un comando
# ----------------------------------------------------------------------

async def avvia_wizard(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    nome_comando: str,
    mostra_menu_al_termine: bool = False,
) -> int:
    """Apre il wizard di un comando saltando la schermata di scelta.

    È il tronco comune fra il click su un pulsante della pulsantiera e un
    comando messo negli entry_points: controllo del ruolo, precondizione,
    esecuzione immediata se il comando non chiede dati. `mostra_menu_al_termine`
    distingue i due casi: dalla pulsantiera si torna alla pulsantiera, da
    /comando la conversazione finisce.
    """
    comando = trova_comando(nome_comando)
    fine = _mostra_menu if mostra_menu_al_termine else _termina

    if comando is None:
        await rispondi(update, "⚠️ Comando non riconosciuto.")
        return await fine(update, context)

    # Il ruolo si ricontrolla qui perché si arriva anche da un comando digitato,
    # non solo da una tastiera. Si usa la stringa e non MESSAGGIO_NEGATO, che non
    # ha una voce per Role.PUBBLICO.
    if ruolo_utente(update, context) < comando.ruolo:
        await rispondi(update, NEGATO)
        return await fine(update, context)

    precondizione = PRECONDIZIONI.get(comando.nome)
    if precondizione is not None:
        try:
            await precondizione(update, context)
        except ErroreValidazione as exc:
            # L'operazione fallirebbe comunque: inutile chiedere i dati.
            await rispondi(update, f"⚠️ {exc}")
            return await fine(update, context)

    if comando.nome == "importa":
        # L'import ha bisogno di un allegato: usciamo dal wizard e aspettiamo il file.
        context.user_data[ATTESA_CSV] = True
        await rispondi(update, ISTRUZIONI)
        return ConversationHandler.END

    if not comando.richiede_input:
        await AZIONI[comando.nome](update, context, {})
        return await fine(update, context)

    context.user_data["wizard"] = {"comando": comando.nome, "valori": {}, "indice": 0}
    return await _chiedi_campo(update, context)


def _entry_wizard(nome: str):
    """L'handler di /comando per i comandi dichiarati wizard_diretto."""

    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        context.user_data.pop("wizard", None)
        if argomenti(update):
            # Questi comandi hanno campi a pulsanti e campi di testo libero pieni
            # di virgole: un parsing degli argomenti sulla stessa riga darebbe due
            # percorsi da mantenere, e una compilazione parziale confonderebbe più
            # di quanto aiuti.
            await rispondi(
                update,
                "ℹ️ Questo comando si compila a passi: ti chiedo i dati uno alla "
                "volta, quindi ho ignorato il testo dopo il comando.",
            )
        return await avvia_wizard(update, context, nome)

    handler.__name__ = f"entry_{nome}"
    return handler


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
    # Qui con un alert, che su un pulsante si vede meglio di una risposta in chat.
    if ruolo_utente(update, context) < comando.ruolo:
        await query.answer(NEGATO, show_alert=True)
        return SCELTA

    await query.answer()
    return await avvia_wizard(update, context, nome, mostra_menu_al_termine=True)


async def on_conferma(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    stato = context.user_data.pop("wizard", None)
    if not stato:
        return await cmd_menu(update, context)

    comando = trova_comando(stato["comando"])
    if comando is None or ruolo_utente(update, context) < comando.ruolo:
        await rispondi(update, NEGATO)
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
    # I comandi con wizard_diretto entrano nel proprio wizard senza passare dalla
    # pulsantiera. Stanno negli entry_points perché la ConversationHandler è
    # registrata prima dei CommandHandler e vincerebbe comunque, e anche nei
    # fallbacks: senza, digitarne uno mentre un altro wizard è in corso non
    # scatterebbe (la conversazione è già attiva) e, essendo un comando, sarebbe
    # escluso dal MessageHandler e finirebbe nel catch-all.
    entry_diretti = [
        CommandHandler(c.nome, _entry_wizard(c.nome)) for c in COMMANDS if c.wizard_diretto
    ]
    return ConversationHandler(
        entry_points=[CommandHandler("menu", cmd_menu)] + entry_diretti + scelta_handlers,
        states={
            SCELTA: scelta_handlers,
            RACCOLTA: [
                CallbackQueryHandler(on_opzione, pattern=r"^menu:opt:\d+:\d+$"),
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
        ]
        + entry_diretti,
        conversation_timeout=DURATA_MASSIMA,
        name="menu",
    )
