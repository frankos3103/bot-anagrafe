"""Il Registro Pubblico delle Attività: proposta, approvazione, rimozione.

Un cittadino **propone** la propria attività; nel registro non entra nulla
finché un amministratore non **approva**. All'approvazione l'attività viene
iscritta e la sua scheda pubblicata sulla Gazzetta Ciompista; al rifiuto la
proposta viene cancellata e nel database non resta traccia.

Dopo l'approvazione l'attività si può rimuovere: il proprietario ritira la
propria (stato CHIUSA), un amministratore la rimuove d'ufficio (RIMOSSA).
"""

from __future__ import annotations

import io
import logging
import sqlite3

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputFile, Update
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from .. import controlli, repository
from ..commands import (
    ETICHETTE_FORMATO,
    etichetta_tipologia,
    render_uso,
    trova_comando,
)
from ..esportazione import FORMATO_PREDEFINITO, esporta_attivita
from ..formatting import (
    escape_markdown_legacy,
    riga_attivita,
    scheda_proposta,
    spezza_in_blocchi,
)
from ..logbook import fmt_username, fmt_utente, send_log
from ..validators import ErroreValidazione, valida_attivita_id, valida_scelta
from .common import argomenti, db, get_roles, rispondi
from .gazzetta import POST_CANCELLATO, POST_FALLITO, chiudi_post, pubblica_attivita
from .notifiche import aggiorna_copie_notifica, avvisa_in_privato, invia_notifiche_admin

logger = logging.getLogger(__name__)

Valori = dict

# Un ritiro volontario e un atto d'ufficio si raccontano in modo diverso, pur
# producendo lo stesso effetto sull'elenco pubblico.
VERBO_RIMOZIONE = {
    repository.ATTIVITA_CHIUSA: "ritirata dal proprietario",
    repository.ATTIVITA_RIMOSSA: "rimossa d'ufficio",
}

AVVISO_GAZZETTA = (
    "⚠️ Non sono riuscito a togliere il post dalla Gazzetta Ciompista: "
    "rimuovilo a mano."
)


def tastiera_proposta(proposta_id: int) -> InlineKeyboardMarkup:
    """I due pulsanti dell'esame: approvare o rifiutare."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "✅ Approva", callback_data=f"attivita:approva:{proposta_id}"
                ),
                InlineKeyboardButton(
                    "❌ Rifiuta", callback_data=f"attivita:rifiuta:{proposta_id}"
                ),
            ]
        ]
    )


# ----------------------------------------------------------------------
# Proposta
# ----------------------------------------------------------------------

async def azione_registra_attivita(
    update: Update, context: ContextTypes.DEFAULT_TYPE, valori: Valori
) -> None:
    """Propone l'attività e la manda all'esame degli amministratori."""
    utente = update.effective_user
    nome = valori["nome_attivita"]

    with db(context) as conn:
        try:
            # Le precondizioni hanno già girato all'inizio del wizard, ma fra il
            # primo passo e la conferma il cittadino può essere stato rimosso
            # dall'anagrafe e il nome può essere stato occupato.
            cittadino = controlli.precondizione_attivita(conn, utente.id)
            controlli.verifica_nome_attivita_libero(conn, utente.id, nome)
            proposta_id = repository.crea_proposta(
                conn,
                owner_id=utente.id,
                owner_username=utente.username,
                nome_attivita=nome,
                tipologia=valori["tipologia"],
                descrizione=valori["descrizione"],
                contatto_link=valori.get("contatto_link"),
            )
        except ErroreValidazione as exc:
            await rispondi(update, f"⚠️ {exc}")
            return
        except sqlite3.IntegrityError:
            # L'indice unico: due conferme nello stesso istante.
            await rispondi(
                update, f"⚠️ Hai già proposto un'attività con il nome «{nome}»."
            )
            return

        proposta = repository.get_proposta(conn, proposta_id)

    await rispondi(
        update,
        f"⏳ Proposta #{proposta_id} inviata!\n"
        f"🏪 {nome}\n\n"
        "Un amministratore la esaminerà a breve. L'attività comparirà nel "
        "Registro Pubblico e sulla Gazzetta Ciompista solo dopo l'approvazione.",
    )

    notifiche, non_raggiungibili = await invia_notifiche_admin(
        context,
        get_roles(context).tutti_gli_admin(),
        scheda_proposta(proposta, cittadino),
        tastiera_proposta(proposta_id),
    )
    with db(context) as conn:
        repository.set_proposta_notifiche(conn, proposta_id, notifiche)

    await send_log(
        context,
        f"⏳ *Attività proposta* #{proposta_id}\n"
        f"Da: {fmt_utente(utente)}\n"
        f"{escape_markdown_legacy(nome)} — "
        f"{etichetta_tipologia(valori['tipologia'])}",
    )

    if non_raggiungibili and update.effective_chat.type != "private":
        await rispondi(
            update,
            "⚠️ Attenzione: non sono riuscito a notificare in privato "
            f"{len(non_raggiungibili)} amministratore/i. Devono prima avviare "
            "una chat privata con il bot (premendo /start in privato) per poter "
            "esaminare le proposte.",
        )


# ----------------------------------------------------------------------
# Consultazione pubblica ed export
# ----------------------------------------------------------------------

async def azione_elenco_attivita(
    update: Update, context: ContextTypes.DEFAULT_TYPE, valori: Valori
) -> None:
    with db(context) as conn:
        righe = repository.list_attivita_attive(conn)
        in_attesa = repository.count_proposte(conn)

    if not righe:
        testo = "Il Registro Pubblico delle Attività è vuoto."
        if in_attesa:
            testo += (
                f"\nCi sono {in_attesa} proposte in attesa di approvazione."
            )
        await rispondi(update, testo)
        return

    intestazione = f"📋 *Registro Pubblico delle Attività* \\({len(righe)}\\)"
    for blocco in spezza_in_blocchi([riga_attivita(r) for r in righe], intestazione):
        await rispondi(update, blocco, parse_mode="MarkdownV2")


async def azione_esporta_attivita(
    update: Update, context: ContextTypes.DEFAULT_TYPE, valori: Valori
) -> None:
    """Esporta le attività approvate: il CSV si reimporta con /importa_attivita."""
    with db(context) as conn:
        righe = repository.list_attivita_attive(conn)

    if not righe:
        await rispondi(update, "Il Registro Pubblico delle Attività è vuoto.")
        return

    formato = valori.get("formato") or FORMATO_PREDEFINITO
    documento = esporta_attivita(righe, formato)
    allegato = InputFile(io.BytesIO(documento.contenuto), filename=documento.nome_file)
    await update.effective_message.reply_document(
        document=allegato,
        caption=f"Registro delle Attività — {len(righe)} attività attive.",
    )


async def cmd_elenco_attivita(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    await azione_elenco_attivita(update, context, {})


async def cmd_esporta_attivita(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    grezzo = argomenti(update)
    try:
        formato = (
            valida_scelta(grezzo, ETICHETTE_FORMATO, "Il formato")
            if grezzo
            else FORMATO_PREDEFINITO
        )
    except ErroreValidazione as exc:
        await rispondi(
            update,
            f"⚠️ {exc}\n\n{render_uso(trova_comando('esporta_attivita'))}",
        )
        return
    await azione_esporta_attivita(update, context, {"formato": formato})


# ----------------------------------------------------------------------
# Esame delle proposte
# ----------------------------------------------------------------------

async def _approva(
    update: Update, context: ContextTypes.DEFAULT_TYPE, proposta_id: int
) -> str:
    """Iscrive l'attività proposta e la pubblica.

    Restituisce il testo con cui riscrivere la notifica, o "" se la proposta
    non c'è più o non si è potuta iscrivere.
    """
    query = update.callback_query
    admin = query.from_user

    with db(context) as conn:
        try:
            esito = repository.approva_proposta(
                conn, proposta_id, admin.id, admin.username
            )
        except sqlite3.IntegrityError:
            # Nel frattempo quel nome è stato occupato: la transazione annulla
            # anche la cancellazione, quindi la proposta resta in attesa.
            await query.answer(
                "Quel nome risulta ora occupato: la proposta resta in attesa.",
                show_alert=True,
            )
            return ""

        if esito is None:
            return ""

        attivita_id, proposta = esito
        riga = repository.get_attivita(conn, attivita_id)

    riferimento = await pubblica_attivita(context, riga)
    if riferimento is not None:
        with db(context) as conn:
            repository.set_attivita_post(conn, attivita_id, *riferimento)
        esito_post = "📢 Pubblicata sulla Gazzetta Ciompista."
    else:
        esito_post = (
            "⚠️ La Gazzetta Ciompista non è raggiungibile: l'attività è iscritta "
            "ma non ancora pubblicata."
        )

    nome = proposta["nome_attivita"]
    await avvisa_in_privato(
        context,
        proposta["owner_id"],
        f"🎉 La tua attività «{nome}» è stata approvata!\n"
        f"È iscritta al Registro Pubblico delle Attività con l'ID #{attivita_id}.",
    )

    await send_log(
        context,
        f"✅ *Attività approvata* #{attivita_id}\n"
        f"{escape_markdown_legacy(nome)} — "
        f"{etichetta_tipologia(proposta['tipologia'])}\n"
        f"Proprietario: {fmt_username(proposta['owner_username'])} "
        f"(Telegram ID {proposta['owner_id']})\n"
        f"Approvata da: {fmt_utente(admin)}",
    )

    admin_username = f"@{admin.username}" if admin.username else admin.full_name
    return (
        f"✅ Proposta #{proposta_id} approvata da {admin_username}.\n"
        f"{nome} è ora l'attività #{attivita_id}.\n\n{esito_post}"
    )


async def _rifiuta(
    update: Update, context: ContextTypes.DEFAULT_TYPE, proposta_id: int
) -> str:
    """Cancella la proposta: nel registro non entra nulla e non resta traccia."""
    query = update.callback_query
    admin = query.from_user

    with db(context) as conn:
        proposta = repository.rifiuta_proposta(conn, proposta_id)

    if proposta is None:
        return ""

    nome = proposta["nome_attivita"]
    await avvisa_in_privato(
        context,
        proposta["owner_id"],
        f"❌ La tua proposta di attività «{nome}» non è stata approvata, "
        "e non è stata iscritta al Registro Pubblico delle Attività.",
    )

    await send_log(
        context,
        f"❌ *Proposta rifiutata* #{proposta_id}\n"
        f"{escape_markdown_legacy(nome)} — "
        f"{etichetta_tipologia(proposta['tipologia'])}\n"
        f"Proprietario: {fmt_username(proposta['owner_username'])} "
        f"(Telegram ID {proposta['owner_id']})\n"
        f"Rifiutata da: {fmt_utente(admin)}",
    )

    admin_username = f"@{admin.username}" if admin.username else admin.full_name
    return f"❌ Proposta #{proposta_id} rifiutata da {admin_username}.\n{nome}"


async def on_attivita_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """I pulsanti dell'esame: «attivita:approva:<id>» e «attivita:rifiuta:<id>»."""
    query = update.callback_query
    admin = query.from_user

    if not get_roles(context).is_admin(admin.id):
        await query.answer(
            "Non sei autorizzato a esaminare le proposte di attività.",
            show_alert=True,
        )
        return

    try:
        _, azione, proposta_id_str = query.data.split(":")
        proposta_id = int(proposta_id_str)
    except (ValueError, AttributeError):
        await query.answer("Richiesta non valida.", show_alert=True)
        return

    if azione not in ("approva", "rifiuta"):
        await query.answer("Azione non riconosciuta.", show_alert=True)
        return

    # Le notifiche si leggono prima: approvare o rifiutare cancella la proposta,
    # e senza i loro riferimenti le copie degli altri admin resterebbero attive.
    with db(context) as conn:
        proposta = repository.get_proposta(conn, proposta_id)
    notifiche_json = proposta["notifiche"] if proposta is not None else None

    if azione == "approva":
        testo_finale = await _approva(update, context, proposta_id)
    else:
        testo_finale = await _rifiuta(update, context, proposta_id)

    if not testo_finale:
        # La proposta non c'è più: un altro amministratore ha già deciso. Se
        # l'iscrizione è stata respinta, invece, _approva ha già mostrato il
        # suo alert e la proposta è ancora in attesa: la tastiera resta.
        with db(context) as conn:
            resta = repository.get_proposta(conn, proposta_id) is not None
        if resta:
            return

        await query.answer("Questa proposta è già stata esaminata.", show_alert=True)
        try:
            # La tastiera stantia va via comunque, anche se l'aggiornamento
            # della copia era fallito quando ha deciso l'altro amministratore.
            await query.edit_message_text(
                f"⚠️ Proposta #{proposta_id}: già esaminata da un altro "
                "amministratore.",
                reply_markup=InlineKeyboardMarkup([]),
            )
        except TelegramError as exc:
            logger.warning("Impossibile aggiornare la notifica stantia: %s", exc)
        return

    await query.answer("Approvata." if azione == "approva" else "Rifiutata.")
    corrente = (query.message.chat_id, query.message.message_id)
    await query.edit_message_text(testo_finale, reply_markup=InlineKeyboardMarkup([]))
    await aggiorna_copie_notifica(
        context, notifiche_json, testo_finale, salta=corrente
    )


# ----------------------------------------------------------------------
# Rimozione di un'attività già approvata
# ----------------------------------------------------------------------

async def azione_rimuovi_attivita(
    update: Update, context: ContextTypes.DEFAULT_TYPE, valori: Valori
) -> None:
    """Il proprietario ritira la propria attività, l'admin la rimuove d'ufficio."""
    utente = update.effective_user
    attivita_id = valori["attivita"]
    e_admin = get_roles(context).is_admin(utente.id)

    with db(context) as conn:
        try:
            # Ricontrollato qui: fra il wizard e la conferma la proprietà o lo
            # stato possono essere cambiati.
            riga = controlli.verifica_attivita_rimovibile(
                conn, attivita_id, utente.id, e_admin
            )
        except ErroreValidazione as exc:
            await rispondi(update, f"⚠️ {exc}")
            return

        # Lo stato dipende da chi agisce, non dal ruolo: un amministratore che
        # ritira la *propria* attività fa un ritiro volontario, non un atto
        # d'ufficio.
        proprio = riga["owner_id"] == utente.id
        stato = (
            repository.ATTIVITA_CHIUSA if proprio else repository.ATTIVITA_RIMOSSA
        )

        if not repository.chiudi_attivita(
            conn, attivita_id, stato, utente.id, utente.username
        ):
            aggiornata = repository.get_attivita(conn, attivita_id)
            etichetta = repository.ETICHETTE_STATO_ATTIVITA.get(
                aggiornata["stato"], aggiornata["stato"]
            )
            await rispondi(
                update, f"⚠️ L'attività #{attivita_id} è già {etichetta}."
            )
            return

    nome = riga["nome_attivita"]
    conferma = (
        f"✅ Attività #{attivita_id} «{nome}» "
        f"{'ritirata dal Registro Pubblico' if proprio else 'rimossa dal Registro'}."
    )

    esito_post = await chiudi_post(context, riga)
    if esito_post == POST_CANCELLATO:
        with db(context) as conn:
            repository.set_attivita_post(conn, attivita_id, None, None)
    elif esito_post == POST_FALLITO:
        conferma += f"\n\n{AVVISO_GAZZETTA}"

    await rispondi(update, conferma)

    if not proprio:
        await avvisa_in_privato(
            context,
            riga["owner_id"],
            f"➖ La tua attività «{nome}» (#{attivita_id}) è stata rimossa "
            "d'ufficio dal Registro Pubblico delle Attività.",
        )

    await send_log(
        context,
        f"➖ *Attività {VERBO_RIMOZIONE[stato]}* #{attivita_id}\n"
        f"{escape_markdown_legacy(nome)} — "
        f"{etichetta_tipologia(riga['tipologia'])}\n"
        f"Proprietario: {fmt_username(riga['owner_username'])} "
        f"(Telegram ID {riga['owner_id']})\n"
        f"Da: {fmt_utente(utente)}",
    )

    if esito_post == POST_FALLITO:
        await send_log(
            context,
            f"⚠️ *Gazzetta non aggiornata* — attività #{attivita_id}\n"
            "Il post pubblico non si è potuto né cancellare né riscrivere: "
            "va rimosso a mano.",
        )


async def cmd_rimuovi_attivita(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    try:
        attivita_id = valida_attivita_id(argomenti(update))
    except ErroreValidazione as exc:
        await rispondi(
            update,
            f"⚠️ {exc}\n\n{render_uso(trova_comando('rimuovi_attivita'))}",
        )
        return
    await azione_rimuovi_attivita(update, context, {"attivita": attivita_id})
