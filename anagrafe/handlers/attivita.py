"""Il Registro Pubblico delle Attività (D.M. n.3 del 13/10/2026).

Un cittadino iscrive la propria attività e questa è attiva subito: il decreto
non prevede un'approvazione preventiva. La scheda viene pubblicata sulla
Gazzetta Ciompista e il Ministero dell'Interno (gli amministratori) riceve una
notifica con i pulsanti per rifiutarla o eliminarla d'ufficio: il controllo è
successivo, non preventivo.
"""

from __future__ import annotations

import logging
import sqlite3

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from .. import controlli, repository
from ..commands import etichetta_tipologia, render_uso, trova_comando
from ..formatting import (
    escape_markdown_legacy,
    riga_attivita,
    scheda_moderazione,
    spezza_in_blocchi,
)
from ..logbook import fmt_username, fmt_utente, send_log
from ..roles import Role
from ..validators import ErroreValidazione, valida_attivita_id
from .common import argomenti, db, get_roles, richiede, rispondi
from .gazzetta import POST_CANCELLATO, POST_FALLITO, chiudi_post, pubblica_attivita
from .notifiche import aggiorna_copie_notifica, avvisa_in_privato, invia_notifiche_admin

logger = logging.getLogger(__name__)

Valori = dict

# I due verbi del decreto: «rifiutare» una voce illegittima o legata a un
# profilo non riconosciuto, «eliminare» una voce dal Registro. Spariscono
# entrambe dall'elenco pubblico; la distinzione resta agli atti.
AZIONI_MODERAZIONE = {
    "rifiuta": repository.ATTIVITA_RIFIUTATA,
    "elimina": repository.ATTIVITA_RIMOSSA,
}

VERBO_MODERAZIONE = {
    repository.ATTIVITA_RIFIUTATA: "rifiutata",
    repository.ATTIVITA_RIMOSSA: "eliminata dal Registro",
}

EMOJI_MODERAZIONE = {
    repository.ATTIVITA_RIFIUTATA: "❌",
    repository.ATTIVITA_RIMOSSA: "➖",
}

AVVISO_GAZZETTA = (
    "⚠️ Non sono riuscito a togliere il post dalla Gazzetta Ciompista: "
    "rimuovilo a mano."
)


def tastiera_moderazione(attivita_id: int) -> InlineKeyboardMarkup:
    """I pulsanti riservati al Ministero dell'Interno."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "❌ Rifiuta", callback_data=f"attivita:rifiuta:{attivita_id}"
                ),
                InlineKeyboardButton(
                    "➖ Elimina", callback_data=f"attivita:elimina:{attivita_id}"
                ),
            ]
        ]
    )


# ----------------------------------------------------------------------
# Iscrizione
# ----------------------------------------------------------------------

async def azione_attivita(
    update: Update, context: ContextTypes.DEFAULT_TYPE, valori: Valori
) -> None:
    """Iscrive l'attività, la pubblica in Gazzetta e avvisa il Ministero."""
    utente = update.effective_user
    nome = valori["nome_attivita"]

    with db(context) as conn:
        try:
            # Le precondizioni hanno già girato all'inizio del wizard, ma fra il
            # primo passo e la conferma il cittadino può essere stato rimosso
            # dall'anagrafe e il nome può essere stato occupato.
            cittadino = controlli.precondizione_attivita(conn, utente.id)
            controlli.verifica_nome_attivita_libero(conn, utente.id, nome)
            attivita_id = repository.create_attivita(
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
            # L'indice unico parziale: due conferme nello stesso istante.
            await rispondi(
                update,
                f"⚠️ Hai già registrato un'attività con il nome «{nome}».",
            )
            return

        riga = repository.get_attivita(conn, attivita_id)

    riferimento = await pubblica_attivita(context, riga)
    if riferimento is not None:
        with db(context) as conn:
            repository.set_attivita_post(conn, attivita_id, *riferimento)
        esito_pubblicazione = "📢 La scheda è stata pubblicata sulla Gazzetta Ciompista."
    else:
        esito_pubblicazione = (
            "⚠️ La Gazzetta Ciompista non è raggiungibile: l'attività è iscritta "
            "ma non ancora pubblicata."
        )

    await rispondi(
        update,
        "✅ Attività iscritta al Registro Pubblico delle Attività!\n"
        f"🆔 ID attività: #{attivita_id}\n"
        f"🏪 Nome: {nome}\n\n"
        f"{esito_pubblicazione}",
    )

    notifiche, non_raggiungibili = await invia_notifiche_admin(
        context,
        get_roles(context).tutti_gli_admin(),
        scheda_moderazione(riga, cittadino),
        tastiera_moderazione(attivita_id),
    )
    with db(context) as conn:
        repository.set_attivita_notifiche(conn, attivita_id, notifiche)

    await send_log(
        context,
        f"➕ *Attività iscritta* #{attivita_id}\n"
        f"Da: {fmt_utente(utente)}\n"
        f"{escape_markdown_legacy(nome)} — "
        f"{etichetta_tipologia(valori['tipologia'])}",
    )

    if non_raggiungibili and update.effective_chat.type != "private":
        await rispondi(
            update,
            "⚠️ Attenzione: non sono riuscito a notificare in privato "
            f"{len(non_raggiungibili)} amministratore/i del Ministero. Devono "
            "prima avviare una chat privata con il bot (premendo /start in "
            "privato) per poter ricevere le notifiche del Registro.",
        )


# ----------------------------------------------------------------------
# Consultazione pubblica
# ----------------------------------------------------------------------

async def azione_elenco_attivita(
    update: Update, context: ContextTypes.DEFAULT_TYPE, valori: Valori
) -> None:
    with db(context) as conn:
        righe = repository.list_attivita_attive(conn)

    if not righe:
        await rispondi(update, "Il Registro Pubblico delle Attività è vuoto.")
        return

    intestazione = f"📋 *Registro Pubblico delle Attività* \\({len(righe)}\\)"
    for blocco in spezza_in_blocchi([riga_attivita(r) for r in righe], intestazione):
        await rispondi(update, blocco, parse_mode="MarkdownV2")


# ----------------------------------------------------------------------
# Moderazione
# ----------------------------------------------------------------------

@richiede(Role.ADMIN)
async def azione_modera_attivita(
    update: Update, context: ContextTypes.DEFAULT_TYPE, valori: Valori
) -> None:
    """Rimanda la scheda di un'attività, per moderare anche a notifica persa."""
    with db(context) as conn:
        try:
            riga = controlli.risolvi_attivita(conn, valori["attivita"])
        except ErroreValidazione as exc:
            await rispondi(update, f"⚠️ {exc}")
            return
        cittadino = repository.get_citizen_by_telegram_id(conn, riga["owner_id"])

    attiva = riga["stato"] == repository.ATTIVITA_ATTIVA
    await rispondi(
        update,
        scheda_moderazione(riga, cittadino),
        reply_markup=tastiera_moderazione(riga["attivita_id"]) if attiva else None,
    )


async def on_attivita_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    admin = query.from_user

    if not get_roles(context).is_admin(admin.id):
        await query.answer(
            "Non sei autorizzato a moderare il Registro delle Attività.",
            show_alert=True,
        )
        return

    try:
        _, azione, attivita_id_str = query.data.split(":")
        attivita_id = int(attivita_id_str)
    except (ValueError, AttributeError):
        await query.answer("Richiesta non valida.", show_alert=True)
        return

    stato = AZIONI_MODERAZIONE.get(azione)
    if stato is None:
        await query.answer("Azione non riconosciuta.", show_alert=True)
        return

    with db(context) as conn:
        riga = repository.get_attivita(conn, attivita_id)
        if riga is None:
            await query.answer("Attività non trovata.", show_alert=True)
            return

        # È l'UPDATE condizionato a decidere, non una lettura precedente: due
        # amministratori che premono il pulsante nello stesso istante non
        # producono due moderazioni.
        if not repository.chiudi_attivita(
            conn, attivita_id, stato, admin.id, admin.username
        ):
            aggiornata = repository.get_attivita(conn, attivita_id)
            etichetta = repository.ETICHETTE_STATO_ATTIVITA.get(
                aggiornata["stato"], aggiornata["stato"]
            )
            await query.answer(
                f"Questa attività è già {etichetta}.", show_alert=True
            )
            # La tastiera stantia va via comunque.
            await query.edit_message_text(
                f"⚠️ Attività #{attivita_id}: moderazione già registrata da "
                f"{fmt_username(aggiornata['admin_username'])}.",
                reply_markup=InlineKeyboardMarkup([]),
            )
            return

    admin_username = f"@{admin.username}" if admin.username else admin.full_name
    nominativo = f"{riga['nome_attivita']}"
    emoji = EMOJI_MODERAZIONE[stato]
    testo_finale = (
        f"{emoji} Attività #{attivita_id} {VERBO_MODERAZIONE[stato]} "
        f"da {admin_username}.\n{nominativo}"
    )

    esito_post = await chiudi_post(context, riga)
    if esito_post == POST_CANCELLATO:
        with db(context) as conn:
            repository.set_attivita_post(conn, attivita_id, None, None)
    elif esito_post == POST_FALLITO:
        testo_finale += f"\n\n{AVVISO_GAZZETTA}"

    await query.answer(f"Attività {VERBO_MODERAZIONE[stato]}.")
    corrente = (query.message.chat_id, query.message.message_id)
    await query.edit_message_text(testo_finale, reply_markup=InlineKeyboardMarkup([]))
    await aggiorna_copie_notifica(
        context, riga["notifiche"], testo_finale, salta=corrente
    )

    if stato == repository.ATTIVITA_RIFIUTATA:
        avviso = (
            f"❌ La tua attività «{nominativo}» (#{attivita_id}) è stata "
            "rifiutata dal Ministero dell'Interno perché non conforme al "
            "Decreto Ministeriale n.3 del 13/10/2026."
        )
    else:
        avviso = (
            f"➖ La tua attività «{nominativo}» (#{attivita_id}) è stata rimossa "
            "d'ufficio dal Registro Pubblico delle Attività."
        )
    await avvisa_in_privato(context, riga["owner_id"], avviso)

    await send_log(
        context,
        f"{emoji} *Attività {VERBO_MODERAZIONE[stato]}* #{attivita_id}\n"
        f"{escape_markdown_legacy(nominativo)} — "
        f"{etichetta_tipologia(riga['tipologia'])}\n"
        f"Proprietario: {fmt_username(riga['owner_username'])} "
        f"(Telegram ID {riga['owner_id']})\n"
        f"Gestita da: {admin_username}",
    )

    if esito_post == POST_FALLITO:
        await send_log(
            context,
            f"⚠️ *Gazzetta non aggiornata* — attività #{attivita_id}\n"
            "Il post pubblico non si è potuto né cancellare né riscrivere: "
            "va rimosso a mano.",
        )


# ----------------------------------------------------------------------
# Comandi testuali
# ----------------------------------------------------------------------

async def cmd_elenco_attivita(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    await azione_elenco_attivita(update, context, {})


async def cmd_modera_attivita(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    try:
        attivita_id = valida_attivita_id(argomenti(update))
    except ErroreValidazione as exc:
        await rispondi(
            update, f"⚠️ {exc}\n\n{render_uso(trova_comando('modera_attivita'))}"
        )
        return
    await azione_modera_attivita(update, context, {"attivita": attivita_id})
