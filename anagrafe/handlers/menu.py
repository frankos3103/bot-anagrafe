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

from telegram.error import TelegramError

from ..commands import (
    COMMANDS,
    Campo,
    Comando,
    Sezione,
    comandi_per_ruolo,
    sezioni_per_ruolo,
    trova_comando,
    trova_sezione,
)
from ..validators import ErroreValidazione
from .azioni import AZIONI
from .common import argomenti, rispondi, ruolo_utente
from .controlli import PRECONDIZIONI, VERIFICHE_CAMPO
from .importazione import ATTESA_CSV, istruzioni
from .scelte import FORNITORI

logger = logging.getLogger(__name__)

SCELTA, RACCOLTA, CONFERMA = range(3)

DURATA_MASSIMA = 300  # secondi di inattività prima che il wizard scada

# Chiave in user_data: l'area in cui l'utente sta lavorando, per riportarlo
# li' dopo ogni comando invece di rimandarlo alla vista principale.
CHIAVE_SEZIONE = "sezione"

TESTO_SEZIONI = (
    "⌨️ Pulsantiera comandi\n\n"
    "Scegli l'area su cui vuoi operare."
)

TESTO_SEZIONE = (
    "Scegli un'azione: quelle che richiedono dei dati te li chiederanno "
    "un passo alla volta."
)

NEGATO = "⛔ Non sei autorizzato a usare questo comando."

BOTTONE_ANNULLA = InlineKeyboardButton("❌ Annulla", callback_data="menu:annulla")
BOTTONE_SALTA = InlineKeyboardButton("⏭ Salta", callback_data="menu:salta")
# Quante scelte per pagina. Oltre la decina la tastiera diventa un muro, e
# Telegram comunque non accetta tastiere illimitate.
SCELTE_PER_PAGINA = 8

BOTTONE_INDIETRO = InlineKeyboardButton("⬅️ Indietro", callback_data="menu:home")
BOTTONE_CHIUDI = InlineKeyboardButton("✖️ Chiudi", callback_data="menu:chiudi")


# ----------------------------------------------------------------------
# Costruzione della tastiera
# ----------------------------------------------------------------------

def tastiera_sezioni(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> InlineKeyboardMarkup:
    """Un pulsante per ogni area in cui il ruolo di chi guarda ha qualcosa da fare."""
    sezioni = sezioni_per_ruolo(ruolo_utente(update, context))
    righe = [
        [InlineKeyboardButton(s.label, callback_data=f"menu:sez:{s.chiave}")]
        for s in sezioni
    ]
    righe.append([BOTTONE_CHIUDI])
    return InlineKeyboardMarkup(righe)


def tastiera_sezione(
    update: Update, context: ContextTypes.DEFAULT_TYPE, sezione: Sezione
) -> InlineKeyboardMarkup:
    """I comandi di quell'area permessi al ruolo di chi guarda."""
    comandi = comandi_per_ruolo(
        ruolo_utente(update, context), solo_menu=True, sezione=sezione.chiave
    )
    bottoni = [
        InlineKeyboardButton(c.label, callback_data=f"menu:cmd:{c.nome}") for c in comandi
    ]
    righe = [bottoni[i : i + 2] for i in range(0, len(bottoni), 2)]
    righe.append([BOTTONE_INDIETRO, BOTTONE_CHIUDI])
    return InlineKeyboardMarkup(righe)


async def _invia_o_modifica(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    testo: str,
    tastiera: InlineKeyboardMarkup,
    modifica: bool,
) -> None:
    """Riscrive il messaggio della pulsantiera, oppure ne manda uno nuovo.

    Navigare fra le aree modifica il messaggio invece di aggiungerne uno, così
    la pulsantiera resta un solo messaggio e non riempie la chat. Dopo un
    comando, invece, il messaggio da riscrivere non è più l'ultimo: si manda
    una pulsantiera nuova.
    """
    query = update.callback_query
    if modifica and query is not None:
        if query.message is not None and query.message.text == testo:
            # Stessa vista: la tastiera che l'utente sta guardando va già bene,
            # e Telegram rifiuterebbe una modifica a contenuto identico.
            return
        try:
            await query.edit_message_text(testo, reply_markup=tastiera)
            return
        except TelegramError as exc:
            logger.warning("Impossibile aggiornare la pulsantiera: %s", exc)
    await rispondi(update, testo, reply_markup=tastiera)


async def _mostra_sezioni(
    update: Update, context: ContextTypes.DEFAULT_TYPE, modifica: bool = False
) -> int:
    """La vista principale: si sceglie l'area."""
    await _invia_o_modifica(
        update, context, TESTO_SEZIONI, tastiera_sezioni(update, context), modifica
    )
    return SCELTA


async def _mostra_sezione(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    sezione: Sezione,
    modifica: bool = False,
) -> int:
    testo = f"{sezione.label}\n\n{TESTO_SEZIONE}"
    await _invia_o_modifica(
        update, context, testo, tastiera_sezione(update, context, sezione), modifica
    )
    return SCELTA


def _sezione_corrente(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> Sezione | None:
    """L'area memorizzata, se è ancora valida per chi guarda.

    Può non esserlo più: un ruolo revocato, o una sezione tolta dal registro.
    In quel caso si ricade sulla vista principale, invece di mostrare una
    tastiera con il solo «Indietro».
    """
    chiave = context.user_data.get(CHIAVE_SEZIONE)
    if not chiave:
        return None
    sezione = trova_sezione(chiave)
    if sezione is None or sezione not in sezioni_per_ruolo(ruolo_utente(update, context)):
        context.user_data.pop(CHIAVE_SEZIONE, None)
        return None
    return sezione


async def _mostra_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Il punto di ritorno dopo un comando: l'area da cui si è partiti.

    Lo chiamano on_conferma, on_annulla e avvia_wizard, percio' chi esegue un
    comando resta nella sua area invece di tornare alla vista principale.
    """
    sezione = _sezione_corrente(update, context)
    if sezione is None:
        return await _mostra_sezioni(update, context)
    return await _mostra_sezione(update, context, sezione)


async def _termina(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return ConversationHandler.END


async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """/menu ricomincia sempre dalla scelta dell'area."""
    context.user_data.pop("wizard", None)
    context.user_data.pop(CHIAVE_SEZIONE, None)
    return await _mostra_sezioni(update, context)


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
    indice_campo = stato["indice"]
    righe: list[list[InlineKeyboardButton]] = []

    if campo.a_pulsanti:
        bottoni = [
            InlineKeyboardButton(
                opzione.label, callback_data=f"menu:opt:{indice_campo}:{i}"
            )
            for i, opzione in enumerate(campo.opzioni)
        ]
        passo = max(1, campo.per_riga)
        righe = [bottoni[i : i + passo] for i in range(0, len(bottoni), passo)]

    elif campo.a_scelte:
        # Le scelte lette dal registro: una per riga, perché le etichette sono
        # nomi di persone o di attività e di fianco non ci starebbero.
        scelte = stato.get("scelte") or []
        pagina = stato.get("pagina", 0)
        inizio = pagina * SCELTE_PER_PAGINA
        for indice in range(inizio, min(inizio + SCELTE_PER_PAGINA, len(scelte))):
            _, etichetta = scelte[indice]
            righe.append(
                [
                    InlineKeyboardButton(
                        etichetta, callback_data=f"menu:opt:{indice_campo}:{indice}"
                    )
                ]
            )
        righe.extend(_righe_impaginazione(indice_campo, pagina, len(scelte)))

    righe.append([BOTTONE_SALTA, BOTTONE_ANNULLA] if campo.opzionale else [BOTTONE_ANNULLA])
    return InlineKeyboardMarkup(righe)


def _pagine(totale: int) -> int:
    return max(1, -(-totale // SCELTE_PER_PAGINA))


def _righe_impaginazione(
    indice_campo: int, pagina: int, totale: int
) -> list[list[InlineKeyboardButton]]:
    """Le frecce, solo se c'è più di una pagina."""
    pagine = _pagine(totale)
    if pagine <= 1:
        return []

    riga = []
    if pagina > 0:
        riga.append(
            InlineKeyboardButton(
                "⬅️", callback_data=f"menu:pag:{indice_campo}:{pagina - 1}"
            )
        )
    riga.append(
        InlineKeyboardButton(
            f"{pagina + 1}/{pagine}", callback_data=f"menu:pag:{indice_campo}:{pagina}"
        )
    )
    if pagina < pagine - 1:
        riga.append(
            InlineKeyboardButton(
                "➡️", callback_data=f"menu:pag:{indice_campo}:{pagina + 1}"
            )
        )
    return [riga]


async def _carica_scelte(
    update: Update, context: ContextTypes.DEFAULT_TYPE, campo: Campo
) -> list[list[str]] | None:
    """Interroga il fornitore del campo e memorizza le voci trovate.

    Si memorizzano nel wizard perché i pulsanti portano l'indice nella lista:
    senza la lista, l'indice non si potrebbe più risolvere. Restituisce None se
    il fornitore non è registrato, cosa che un test rende impossibile.
    """
    fornitore = FORNITORI.get(campo.scelte)
    if fornitore is None:
        logger.error("Nessun fornitore di scelte per «%s»", campo.scelte)
        return None

    voci = await fornitore(update, context)
    scelte = [[o.chiave, o.label] for o in voci]
    stato = _wizard(context)
    stato["scelte"] = scelte
    stato["pagina"] = 0
    return scelte


async def _chiedi_campo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Invia il prompt del campo corrente, o passa al riepilogo se sono finiti."""
    corrente = _campo_corrente(context)
    if corrente is None:
        finito = trova_comando(_wizard(context)["comando"])
        if finito is not None and finito.senza_conferma:
            return await _esegui(update, context)
        return await _mostra_riepilogo(update, context)

    comando, campo = corrente
    stato = _wizard(context)

    if campo.a_scelte:
        scelte = await _carica_scelte(update, context, campo)
        if not scelte:
            # Niente da scegliere: proseguire chiederebbe un ID che non esiste.
            await rispondi(
                update,
                campo.messaggio_vuoto
                or "Non c'è nulla da scegliere per questo comando.",
            )
            context.user_data.pop("wizard", None)
            return await _mostra_menu(update, context)

    passo = f"Passo {stato['indice'] + 1} di {len(comando.campi)}"
    testo = f"{comando.emoji} {comando.nome}\n{passo}\n\n{campo.prompt}"
    if campo.a_pulsanti:
        testo += "\n\n(scegli con i pulsanti, oppure scrivi la risposta)"
    elif campo.a_scelte:
        totale = len(stato.get("scelte") or [])
        testo += f"\n\n({totale} voci"
        if _pagine(totale) > 1:
            testo += ", sfogliale con le frecce"
        testo += "; puoi anche scrivere la risposta)"
    if campo.opzionale:
        testo += "\n\n(facoltativo: premi «Salta» per lasciarlo vuoto)"

    await rispondi(update, testo, reply_markup=_tastiera_campo(stato, campo))
    return RACCOLTA


async def _mostra_riepilogo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    stato = _wizard(context)
    comando = trova_comando(stato["comando"])
    righe = [f"{comando.emoji} Conferma «{comando.nome}»", ""]
    etichette = stato.get("etichette", {})
    for campo in comando.campi:
        # Per una scelta letta dal registro si mostra l'etichetta del pulsante
        # («Mario ROSSI»), non il valore tecnico che ci sta sotto («#12»).
        mostrato = etichette.get(campo.chiave) or campo.mostra(
            stato["valori"].get(campo.chiave)
        )
        righe.append(f"• {campo.etichetta}: {mostrato}")

    tastiera = InlineKeyboardMarkup(
        [[InlineKeyboardButton("✅ Conferma", callback_data="menu:conferma"), BOTTONE_ANNULLA]]
    )
    await rispondi(update, "\n".join(righe), reply_markup=tastiera)
    return CONFERMA


async def _registra_valore(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    grezzo: str,
    etichetta: str | None = None,
) -> int:
    """Valida il valore del campo corrente, lo salva e avanza di un passo.

    È il percorso unico del testo e dei pulsanti: anche una scelta fatta a
    pulsante passa dal validatore del campo e dalle VERIFICHE_CAMPO, così il
    valore salvato è sempre nella forma canonica.

    `etichetta` è il testo del pulsante premuto, da mostrare nel riepilogo al
    posto del valore tecnico. Si assegna qui insieme al valore, e si cancella
    quando il valore arriva scritto: altrimenti chi sceglie col pulsante, sbaglia
    e poi riscrive si vedrebbe nel riepilogo l'etichetta della scelta vecchia.
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
    if etichetta:
        stato.setdefault("etichette", {})[campo.chiave] = etichetta
    else:
        stato.get("etichette", {}).pop(campo.chiave, None)
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
    stato = _wizard(context)
    try:
        _, _, indice_campo, indice_opzione = query.data.split(":")
        indice_campo, indice_opzione = int(indice_campo), int(indice_opzione)
    except ValueError:
        await query.answer("Scelta non riconosciuta.", show_alert=True)
        return RACCOLTA

    # Le scelte lette dal registro sono memorizzate nel wizard: è lì che
    # l'indice del pulsante si risolve, non nel registro dei comandi.
    disponibili = stato.get("scelte") or [] if campo.a_scelte else campo.opzioni

    # Una tastiera vecchia (un passo già superato, o un wizard precedente ancora
    # in cronologia) non deve poter scrivere nel campo sbagliato.
    if indice_campo != stato["indice"] or indice_opzione >= len(disponibili):
        await query.answer("Questo pulsante non è più valido.", show_alert=True)
        return await _chiedi_campo(update, context)

    if campo.a_scelte:
        chiave, etichetta = disponibili[indice_opzione]
    else:
        opzione = disponibili[indice_opzione]
        chiave, etichetta = opzione.chiave, opzione.label

    await query.answer(etichetta)
    # L'etichetta serve al riepilogo: «Mario ROSSI» invece di «#12».
    return await _registra_valore(update, context, chiave, etichetta=etichetta)


async def on_pagina(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Le frecce fra le pagine di scelte: «menu:pag:<indice_campo>:<pagina>»."""
    query = update.callback_query
    corrente = _campo_corrente(context)
    if corrente is None:
        await query.answer()
        return await cmd_menu(update, context)

    _, campo = corrente
    stato = _wizard(context)
    try:
        _, _, indice_campo, pagina = query.data.split(":")
        indice_campo, pagina = int(indice_campo), int(pagina)
    except ValueError:
        await query.answer("Pagina non riconosciuta.", show_alert=True)
        return RACCOLTA

    scelte = stato.get("scelte") or []
    if indice_campo != stato["indice"] or not 0 <= pagina < _pagine(len(scelte)):
        await query.answer("Questo pulsante non è più valido.", show_alert=True)
        return RACCOLTA

    if pagina == stato.get("pagina", 0):
        # Il pulsante centrale «2/3» dice solo dove sei: non c'è nulla da fare,
        # e Telegram rifiuterebbe una modifica a contenuto identico.
        await query.answer()
        return RACCOLTA

    stato["pagina"] = pagina
    await query.answer()
    try:
        await query.edit_message_reply_markup(
            reply_markup=_tastiera_campo(stato, campo)
        )
    except TelegramError as exc:
        logger.warning("Impossibile cambiare pagina: %s", exc)
    return RACCOLTA


async def on_salta(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    corrente = _campo_corrente(context)
    if corrente is None:
        return await cmd_menu(update, context)

    _, campo = corrente
    stato = _wizard(context)
    stato["valori"][campo.chiave] = None
    stato.get("etichette", {}).pop(campo.chiave, None)
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

    if comando.attende_allegato:
        # L'import ha bisogno di un allegato: usciamo dal wizard e aspettiamo il
        # file. Si memorizza *quale* import, perché i registri sono più di uno.
        context.user_data[ATTESA_CSV] = comando.nome
        await rispondi(update, istruzioni(comando.nome))
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

async def on_scelta_sezione(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Click su un'area della vista principale: «menu:sez:<chiave>»."""
    query = update.callback_query
    chiave = query.data.split(":", 2)[2]
    sezione = trova_sezione(chiave)

    # Come per i comandi, si ricontrolla al click: la tastiera potrebbe essere
    # vecchia, e il ruolo di chi la guarda nel frattempo cambiato.
    if sezione is None or sezione not in sezioni_per_ruolo(ruolo_utente(update, context)):
        await query.answer("Area non disponibile.", show_alert=True)
        return await _mostra_sezioni(update, context, modifica=True)

    await query.answer()
    context.user_data[CHIAVE_SEZIONE] = sezione.chiave
    return await _mostra_sezione(update, context, sezione, modifica=True)


async def on_home(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """«⬅️ Indietro»: torna alla scelta dell'area."""
    await update.callback_query.answer()
    context.user_data.pop(CHIAVE_SEZIONE, None)
    return await _mostra_sezioni(update, context, modifica=True)


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


async def _esegui(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Esegue il comando del wizard coi valori raccolti e torna alla pulsantiera.

    Ci si arriva dal pulsante «Conferma», oppure direttamente dall'ultimo campo
    se il comando è dichiarato `senza_conferma`.
    """
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


async def on_conferma(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    return await _esegui(update, context)


async def on_annulla(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("wizard", None)
    context.user_data.pop(ATTESA_CSV, None)
    if update.callback_query:
        await update.callback_query.answer("Annullato.")
    await rispondi(update, "Operazione annullata.")
    return await _mostra_menu(update, context)


async def on_chiudi(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("wizard", None)
    context.user_data.pop(CHIAVE_SEZIONE, None)
    await update.callback_query.answer()
    await update.callback_query.edit_message_text("Pulsantiera chiusa. Riaprila con /menu.")
    return ConversationHandler.END


async def on_timeout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("wizard", None)
    context.user_data.pop(CHIAVE_SEZIONE, None)
    await rispondi(update, "⌛ Pulsantiera scaduta per inattività. Riaprila con /menu.")
    return ConversationHandler.END


def build_menu_handler() -> ConversationHandler:
    # La scelta dell'area avviene nello stesso stato SCELTA della scelta del
    # comando: non serve uno stato nuovo, bastano due pattern in più.
    scelta_handlers = [
        CallbackQueryHandler(on_scelta_sezione, pattern=r"^menu:sez:"),
        CallbackQueryHandler(on_home, pattern=r"^menu:home$"),
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
                CallbackQueryHandler(on_pagina, pattern=r"^menu:pag:\d+:\d+$"),
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
