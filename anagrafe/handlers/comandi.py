"""I comandi testuali: analizzano gli argomenti e delegano alle azioni."""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from ..commands import (
    ETICHETTE_FORMATO,
    render_help,
    render_uso,
    trova_comando,
)
from ..esportazione import FORMATO_PREDEFINITO
from ..validators import (
    ErroreValidazione,
    valida_scelta,
    parse_inserisci,
    parse_richiedi,
    valida_ricerca,
    valida_riferimento_cittadino,
    valida_riferimento_utente,
)
from .azioni import (
    azione_aggiungi_admin,
    azione_cerca_cittadino,
    azione_elenco_cittadini,
    azione_elenco_admin,
    azione_esporta_cittadini,
    azione_inserisci_cittadino,
    azione_richiedi_cittadinanza,
    azione_rimuovi_cittadino,
    azione_rimuovi_admin,
    azione_tagga_cittadini,
)
from .common import argomenti, rispondi, ruolo_utente
from .controlli import PRECONDIZIONI


async def _errore_uso(update: Update, nome_comando: str, exc: ErroreValidazione) -> None:
    comando = trova_comando(nome_comando)
    testo = f"⚠️ {exc}"
    if comando is not None:
        testo += f"\n\n{render_uso(comando)}"
    await rispondi(update, testo)


# ----------------------------------------------------------------------
# Pubblici
# ----------------------------------------------------------------------

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await rispondi(
        update,
        "Benvenuto nel bot del registro cittadini.\n\n"
        + render_help(ruolo_utente(update, context)),
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await rispondi(update, render_help(ruolo_utente(update, context)))


async def cmd_elenco_cittadini(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await azione_elenco_cittadini(update, context, {})


def _formato(update: Update) -> dict:
    """Legge il formato dall'argomento del comando, se c'è.

    Senza argomento si usa il Markdown, che è ciò che l'export produceva prima
    che i formati fossero due: «/esporta_cittadini» continua a funzionare come
    ha sempre funzionato.
    """
    grezzo = argomenti(update)
    if not grezzo:
        return {"formato": FORMATO_PREDEFINITO}
    return {"formato": valida_scelta(grezzo, ETICHETTE_FORMATO, "Il formato")}


async def cmd_esporta_cittadini(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        valori = _formato(update)
    except ErroreValidazione as exc:
        await _errore_uso(update, "esporta_cittadini", exc)
        return
    await azione_esporta_cittadini(update, context, valori)


async def cmd_cerca_cittadino(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        query = valida_ricerca(argomenti(update))
    except ErroreValidazione as exc:
        await _errore_uso(update, "cerca_cittadino", exc)
        return
    await azione_cerca_cittadino(update, context, {"query": query})


async def cmd_richiedi_cittadinanza(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Prima di tutto: se la richiesta è comunque impossibile, è inutile
    # lamentarsi del formato degli argomenti.
    try:
        await PRECONDIZIONI["richiedi_cittadinanza"](update, context)
    except ErroreValidazione as exc:
        await rispondi(update, str(exc))
        return

    try:
        dati = parse_richiedi(argomenti(update))
    except ErroreValidazione as exc:
        await _errore_uso(update, "richiedi_cittadinanza", exc)
        return
    await azione_richiedi_cittadinanza(update, context, {"nome": dati.nome, "cognome": dati.cognome})


# ----------------------------------------------------------------------
# Amministratore
# ----------------------------------------------------------------------

async def cmd_inserisci_cittadino(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        dati = parse_inserisci(argomenti(update))
    except ErroreValidazione as exc:
        await _errore_uso(update, "inserisci_cittadino", exc)
        return
    await azione_inserisci_cittadino(
        update,
        context,
        {
            "telegram_id": dati.telegram_id,
            "username": dati.username,
            "nome": dati.nome,
            "cognome": dati.cognome,
        },
    )


async def cmd_rimuovi_cittadino(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        cittadino = valida_riferimento_cittadino(argomenti(update))
    except ErroreValidazione as exc:
        await _errore_uso(update, "rimuovi_cittadino", exc)
        return
    await azione_rimuovi_cittadino(update, context, {"cittadino": cittadino})


async def cmd_tagga_cittadini(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await azione_tagga_cittadini(update, context, {})


# ----------------------------------------------------------------------
# Root
# ----------------------------------------------------------------------

async def cmd_elenco_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await azione_elenco_admin(update, context, {})


async def cmd_aggiungi_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        utente = valida_riferimento_utente(argomenti(update))
    except ErroreValidazione as exc:
        await _errore_uso(update, "aggiungi_admin", exc)
        return
    await azione_aggiungi_admin(update, context, {"utente": utente})


async def cmd_rimuovi_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        utente = valida_riferimento_utente(argomenti(update))
    except ErroreValidazione as exc:
        await _errore_uso(update, "rimuovi_admin", exc)
        return
    await azione_rimuovi_admin(update, context, {"utente": utente})
