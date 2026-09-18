"""Le azioni vere e proprie del bot.

Ogni azione riceve un dizionario di valori già validati e si occupa di
eseguirla, rispondere in chat e scrivere sul canale di log. Sono condivise fra
i comandi testuali (/inserisci ...) e il wizard di /menu: è così che la
pulsantiera può fare esattamente tutto quello che si fa da riga di comando.
"""

from __future__ import annotations

import io
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputFile, Update
from telegram.error import Forbidden, TelegramError
from telegram.ext import ContextTypes

from .. import controlli, repository
from ..commands import render_help
from ..formatting import (
    format_row,
    riga_elenco,
    spezza_in_blocchi,
    tabella_markdown,
)
from ..logbook import fmt_username, fmt_utente, send_log
from ..roles import ETICHETTE_RUOLO, Role
from ..validators import ErroreValidazione
from .common import db, get_roles, richiede, rispondi, ruolo_utente

logger = logging.getLogger(__name__)

Valori = dict


# ----------------------------------------------------------------------
# Comandi pubblici
# ----------------------------------------------------------------------

async def azione_help(update: Update, context: ContextTypes.DEFAULT_TYPE, valori: Valori) -> None:
    await rispondi(update, render_help(ruolo_utente(update, context)))


async def azione_elenco(update: Update, context: ContextTypes.DEFAULT_TYPE, valori: Valori) -> None:
    with db(context) as conn:
        righe = repository.list_citizens(conn, ordine="nome")

    if not righe:
        await rispondi(update, "Il registro è vuoto.")
        return

    intestazione = f"👥 *Elenco cittadini* \\({len(righe)}\\)"
    blocchi = spezza_in_blocchi([riga_elenco(r) for r in righe], intestazione)
    for blocco in blocchi:
        await rispondi(update, blocco, parse_mode="MarkdownV2")


async def azione_esporta(update: Update, context: ContextTypes.DEFAULT_TYPE, valori: Valori) -> None:
    with db(context) as conn:
        righe = repository.list_citizens(conn, ordine="citizen_id")

    if not righe:
        await rispondi(update, "Il registro è vuoto.")
        return

    contenuto = tabella_markdown(righe, len(righe)).encode("utf-8")
    documento = InputFile(io.BytesIO(contenuto), filename="registro_cittadini.md")
    await update.effective_message.reply_document(
        document=documento,
        caption=f"Registro cittadini — {len(righe)} cittadini totali.",
    )


async def azione_cerca(update: Update, context: ContextTypes.DEFAULT_TYPE, valori: Valori) -> None:
    query = valori["query"]
    with db(context) as conn:
        righe = repository.search_citizens(conn, query)
        suggeriti = [] if righe else repository.suggest_citizens(conn, query)

    if righe:
        intestazione = f"Risultati per «{query}» ({len(righe)}):"
    elif suggeriti:
        righe = suggeriti
        intestazione = f"Nessun risultato esatto per «{query}». Forse cercavi:"
    else:
        await rispondi(update, f"Nessun cittadino trovato per «{query}».")
        return

    for blocco in spezza_in_blocchi([format_row(r) for r in righe], intestazione):
        await rispondi(update, blocco)


# ----------------------------------------------------------------------
# Richiesta di cittadinanza
# ----------------------------------------------------------------------

async def azione_richiedi(update: Update, context: ContextTypes.DEFAULT_TYPE, valori: Valori) -> None:
    utente = update.effective_user
    nome, cognome = valori["nome"], valori["cognome"]

    with db(context) as conn:
        try:
            controlli.precondizione_richiedi(conn, utente.id)
        except ErroreValidazione as exc:
            await rispondi(update, str(exc))
            return

        request_id = repository.create_request(
            conn, utente.id, utente.username, nome, cognome
        )

    await rispondi(
        update,
        f"Richiesta di cittadinanza #{request_id} inviata! "
        "Un amministratore la esaminerà a breve.",
    )

    richiedente = f"@{utente.username}" if utente.username else f"ID {utente.id}"
    tastiera = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Accetta", callback_data=f"richiesta:accetta:{request_id}"),
                InlineKeyboardButton("❌ Rifiuta", callback_data=f"richiesta:rifiuta:{request_id}"),
            ]
        ]
    )
    testo_notifica = (
        f"📋 Nuova richiesta di cittadinanza #{request_id}\n"
        f"Da: {richiedente}\n"
        f"Nome: {nome} {cognome}\n\n"
        "Puoi accettarla o rifiutarla con i pulsanti qui sotto."
    )

    admin_ids = get_roles(context).tutti_gli_admin()
    non_raggiungibili: list[int] = []
    notifiche: list[list[int]] = []

    for admin_id in admin_ids:
        try:
            inviato = await context.bot.send_message(
                chat_id=admin_id, text=testo_notifica, reply_markup=tastiera
            )
            notifiche.append([inviato.chat_id, inviato.message_id])
        except Forbidden:
            # L'admin non ha mai avviato una chat privata con il bot.
            non_raggiungibili.append(admin_id)
            logger.warning(
                "Impossibile notificare l'admin %s: deve avviare prima una chat "
                "privata con il bot (/start).",
                admin_id,
            )
        except TelegramError as exc:
            non_raggiungibili.append(admin_id)
            logger.warning("Errore inviando la notifica all'admin %s: %s", admin_id, exc)

    with db(context) as conn:
        repository.set_request_notifications(conn, request_id, notifiche)

    await send_log(
        context,
        f"📋 *Nuova richiesta di cittadinanza* #{request_id}\n"
        f"Da: {richiedente} (Telegram ID {utente.id})\n"
        f"Nome: {nome} {cognome}",
    )

    if non_raggiungibili and update.effective_chat.type != "private":
        await rispondi(
            update,
            "⚠️ Attenzione: non sono riuscito a notificare in privato "
            f"{len(non_raggiungibili)} amministratore/i. Devono prima avviare una "
            "chat privata con il bot (premendo /start in privato) per poter "
            "ricevere le notifiche delle richieste.",
        )


# ----------------------------------------------------------------------
# Comandi amministratore
# ----------------------------------------------------------------------

@richiede(Role.ADMIN)
async def azione_inserisci(update: Update, context: ContextTypes.DEFAULT_TYPE, valori: Valori) -> None:
    telegram_id = valori["telegram_id"]
    username = valori.get("username")
    nome, cognome = valori["nome"], valori["cognome"]

    with db(context) as conn:
        try:
            controlli.verifica_nuovo_cittadino(conn, telegram_id)
            citizen_id = repository.insert_citizen(
                conn, telegram_id, username, nome, cognome
            )
        except ErroreValidazione as exc:
            await rispondi(update, str(exc))
            return

    conferma = (
        "✅ Cittadino inserito con successo!\n"
        f"ID cittadino: #{citizen_id}\n"
        f"Nome: {nome} {cognome}"
    )
    if username:
        conferma += f"\nUsername: @{username}"
    await rispondi(update, conferma)

    await send_log(
        context,
        f"➕ *Cittadino inserito*\n"
        f"Da: {fmt_utente(update.effective_user)}\n"
        f"Cittadino: #{citizen_id} — {nome} {cognome} — {fmt_username(username)} "
        f"(Telegram ID {telegram_id})",
    )


@richiede(Role.ADMIN)
async def azione_rimuovi(update: Update, context: ContextTypes.DEFAULT_TYPE, valori: Valori) -> None:
    with db(context) as conn:
        try:
            citizen_id = controlli.risolvi_cittadino(conn, valori["cittadino"])["citizen_id"]
        except ErroreValidazione as exc:
            await rispondi(update, str(exc))
            return
        riga = repository.delete_citizen(conn, citizen_id)

    if riga is None:
        await rispondi(update, f"Nessun cittadino trovato con ID #{citizen_id}.")
        return

    tag = f", @{riga['username']}" if riga["username"] else ""
    await rispondi(
        update,
        f"✅ Cittadino #{citizen_id} ({riga['nome']} {riga['cognome']}{tag}) "
        "rimosso dal registro.",
    )

    await send_log(
        context,
        f"➖ *Cittadino rimosso*\n"
        f"Da: {fmt_utente(update.effective_user)}\n"
        f"Cittadino: #{citizen_id} — {riga['nome']} {riga['cognome']} — "
        f"{fmt_username(riga['username'])} (Telegram ID {riga['telegram_id']})",
    )


# ----------------------------------------------------------------------
# Comandi root
# ----------------------------------------------------------------------

def _fmt_admin(conn, admin_id: int) -> str:
    """«123 (@mario)» se l'admin è un cittadino con tag, altrimenti l'ID."""
    riga = repository.get_citizen_by_telegram_id(conn, admin_id)
    if riga is not None and riga["username"]:
        return f"{admin_id} (@{riga['username']})"
    return str(admin_id)


@richiede(Role.ROOT)
async def azione_elenco_admin(update: Update, context: ContextTypes.DEFAULT_TYPE, valori: Valori) -> None:
    roles = get_roles(context)
    with db(context) as conn:
        righe = [
            f"• {_fmt_admin(conn, admin_id)} — {ETICHETTE_RUOLO[roles.role_of(admin_id)]}"
            for admin_id in roles.tutti_gli_admin()
        ]
    await rispondi(update, "👮 Elenco amministratori\n\n" + "\n".join(righe))


@richiede(Role.ROOT)
async def azione_aggiungi_admin(update: Update, context: ContextTypes.DEFAULT_TYPE, valori: Valori) -> None:
    roles = get_roles(context)

    with db(context) as conn:
        try:
            admin_id = controlli.risolvi_telegram_id(conn, valori["utente"])
            controlli.verifica_nuovo_admin(roles, admin_id)
        except ErroreValidazione as exc:
            await rispondi(update, str(exc))
            return
        descrizione = _fmt_admin(conn, admin_id)

    try:
        aggiunto = roles.aggiungi(admin_id)
    except OSError as exc:
        logger.exception("Errore aggiungendo l'admin %s", admin_id)
        await rispondi(update, f"Errore durante il salvataggio: {exc}")
        return

    if not aggiunto:
        await rispondi(update, f"L'ID Telegram {admin_id} è già un amministratore.")
        return

    await rispondi(update, f"✅ {descrizione} aggiunto agli amministratori.")
    await send_log(
        context,
        f"🛡 *Amministratore aggiunto*\n"
        f"Da: {fmt_utente(update.effective_user)}\n"
        f"Nuovo admin: {descrizione}",
    )


@richiede(Role.ROOT)
async def azione_rimuovi_admin(update: Update, context: ContextTypes.DEFAULT_TYPE, valori: Valori) -> None:
    roles = get_roles(context)

    with db(context) as conn:
        try:
            admin_id = controlli.risolvi_telegram_id(conn, valori["utente"])
            controlli.verifica_admin_rimovibile(roles, admin_id)
        except ErroreValidazione as exc:
            await rispondi(update, str(exc))
            return
        descrizione = _fmt_admin(conn, admin_id)

    try:
        rimosso = roles.rimuovi(admin_id)
    except OSError as exc:
        logger.exception("Errore rimuovendo l'admin %s", admin_id)
        await rispondi(update, f"Errore durante il salvataggio: {exc}")
        return

    if not rimosso:
        # Il root non si rimuove e gli altri sono già stati verificati: resta
        # solo il caso di un admin sparito dal file nel frattempo.
        await rispondi(
            update,
            f"L'ID Telegram {admin_id} non risulta nell'elenco degli amministratori.",
        )
        return

    await rispondi(update, f"✅ {descrizione} rimosso dagli amministratori.")
    await send_log(
        context,
        f"🚫 *Amministratore rimosso*\n"
        f"Da: {fmt_utente(update.effective_user)}\n"
        f"Admin rimosso: {descrizione}",
    )


# Mappa nome del comando -> azione. È quello che il wizard di /menu esegue alla
# conferma, ed è la stessa funzione che invoca il comando testuale.
AZIONI = {
    "help": azione_help,
    "elenco": azione_elenco,
    "esporta": azione_esporta,
    "cerca": azione_cerca,
    "richiedi": azione_richiedi,
    "inserisci": azione_inserisci,
    "rimuovi": azione_rimuovi,
    "elenco_admin": azione_elenco_admin,
    "aggiungi_admin": azione_aggiungi_admin,
    "rimuovi_admin": azione_rimuovi_admin,
}
