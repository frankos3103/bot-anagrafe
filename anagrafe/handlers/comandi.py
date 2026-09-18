"""I comandi testuali: analizzano gli argomenti e delegano alle azioni."""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from ..commands import render_help, render_uso, trova_comando
from ..validators import (
    ErroreValidazione,
    parse_inserisci,
    parse_richiedi,
    valida_ricerca,
    valida_riferimento_cittadino,
    valida_riferimento_utente,
)
from .azioni import (
    azione_aggiungi_admin,
    azione_cerca,
    azione_elenco,
    azione_elenco_admin,
    azione_esporta,
    azione_inserisci,
    azione_richiedi,
    azione_rimuovi,
    azione_rimuovi_admin,
)
from .common import rispondi, ruolo_utente
from .controlli import PRECONDIZIONI


def _argomenti(update: Update) -> str:
    """Il testo che segue il comando, senza il comando stesso."""
    testo = (update.effective_message.text or "").strip()
    return testo.partition(" ")[2].strip()


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


async def cmd_elenco(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await azione_elenco(update, context, {})


async def cmd_esporta(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await azione_esporta(update, context, {})


async def cmd_cerca(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        query = valida_ricerca(_argomenti(update))
    except ErroreValidazione as exc:
        await _errore_uso(update, "cerca", exc)
        return
    await azione_cerca(update, context, {"query": query})


async def cmd_richiedi(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Prima di tutto: se la richiesta è comunque impossibile, è inutile
    # lamentarsi del formato degli argomenti.
    try:
        await PRECONDIZIONI["richiedi"](update, context)
    except ErroreValidazione as exc:
        await rispondi(update, str(exc))
        return

    try:
        dati = parse_richiedi(_argomenti(update))
    except ErroreValidazione as exc:
        await _errore_uso(update, "richiedi", exc)
        return
    await azione_richiedi(update, context, {"nome": dati.nome, "cognome": dati.cognome})


# ----------------------------------------------------------------------
# Amministratore
# ----------------------------------------------------------------------

async def cmd_inserisci(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        dati = parse_inserisci(_argomenti(update))
    except ErroreValidazione as exc:
        await _errore_uso(update, "inserisci", exc)
        return
    await azione_inserisci(
        update,
        context,
        {
            "telegram_id": dati.telegram_id,
            "username": dati.username,
            "nome": dati.nome,
            "cognome": dati.cognome,
        },
    )


async def cmd_rimuovi(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        cittadino = valida_riferimento_cittadino(_argomenti(update))
    except ErroreValidazione as exc:
        await _errore_uso(update, "rimuovi", exc)
        return
    await azione_rimuovi(update, context, {"cittadino": cittadino})


# ----------------------------------------------------------------------
# Root
# ----------------------------------------------------------------------

async def cmd_elenco_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await azione_elenco_admin(update, context, {})


async def cmd_aggiungi_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        utente = valida_riferimento_utente(_argomenti(update))
    except ErroreValidazione as exc:
        await _errore_uso(update, "aggiungi_admin", exc)
        return
    await azione_aggiungi_admin(update, context, {"utente": utente})


async def cmd_rimuovi_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        utente = valida_riferimento_utente(_argomenti(update))
    except ErroreValidazione as exc:
        await _errore_uso(update, "rimuovi_admin", exc)
        return
    await azione_rimuovi_admin(update, context, {"utente": utente})
