"""Accettazione e rifiuto delle richieste di cittadinanza (pulsanti in DM)."""

from __future__ import annotations

from telegram import InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from .. import repository
from ..logbook import send_log
from .common import db, get_roles
from .notifiche import aggiorna_copie_notifica, avvisa_in_privato

STATI_LEGGIBILI = {
    repository.STATO_ACCETTATA: "già accettata",
    repository.STATO_RIFIUTATA: "già rifiutata",
}


async def on_richiesta_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    admin = query.from_user

    if not get_roles(context).is_admin(admin.id):
        await query.answer("Non sei autorizzato a gestire le richieste.", show_alert=True)
        return

    try:
        _, azione, request_id_str = query.data.split(":")
        request_id = int(request_id_str)
    except (ValueError, AttributeError):
        await query.answer("Richiesta non valida.", show_alert=True)
        return

    if azione not in ("accetta", "rifiuta"):
        await query.answer("Azione non riconosciuta.", show_alert=True)
        return

    with db(context) as conn:
        riga = repository.get_request(conn, request_id)

        if riga is None:
            await query.answer("Richiesta non trovata.", show_alert=True)
            return

        if riga["stato"] != repository.STATO_IN_ATTESA:
            stato = STATI_LEGGIBILI.get(riga["stato"], riga["stato"])
            await query.answer(f"Questa richiesta è {stato}.", show_alert=True)
            return

        admin_username = f"@{admin.username}" if admin.username else admin.full_name
        corrente = (query.message.chat_id, query.message.message_id)
        nominativo = f"{riga['nome']} {riga['cognome']}"

        if azione == "accetta":
            try:
                citizen_id = repository.insert_citizen(
                    conn,
                    telegram_id=riga["telegram_id"],
                    username=riga["username"],
                    nome=riga["nome"],
                    cognome=riga["cognome"],
                )
            except repository.CittadinoGiaEsistente as exc:
                # Nel frattempo è stato registrato per altra via.
                repository.resolve_request(
                    conn, request_id, repository.STATO_RIFIUTATA, admin.id, admin.username
                )
                await query.answer(
                    "Questo utente è già cittadino, richiesta annullata.", show_alert=True
                )
                testo_finale = (
                    f"⚠️ Richiesta #{request_id} annullata: {nominativo} risultava "
                    f"già cittadino (#{exc.citizen_id})."
                )
                await query.edit_message_text(
                    testo_finale, reply_markup=InlineKeyboardMarkup([])
                )
                await aggiorna_copie_notifica(
                    context, riga["notifiche"], testo_finale, salta=corrente
                )
                await send_log(
                    context,
                    f"⚠️ *Richiesta annullata* #{request_id}\n"
                    f"{nominativo} risultava già cittadino (#{exc.citizen_id}).\n"
                    f"Gestita da: {admin_username}",
                )
                return

            repository.resolve_request(
                conn, request_id, repository.STATO_ACCETTATA, admin.id, admin.username
            )

            await query.answer("Richiesta accettata!")
            testo_finale = (
                f"✅ Richiesta #{request_id} accettata da {admin_username}.\n"
                f"{nominativo} è ora cittadino #{citizen_id}."
            )
            await query.edit_message_text(testo_finale, reply_markup=InlineKeyboardMarkup([]))
            await aggiorna_copie_notifica(
                context, riga["notifiche"], testo_finale, salta=corrente
            )
            await avvisa_in_privato(
                context,
                riga["telegram_id"],
                "🎉 La tua richiesta di cittadinanza è stata accettata!\n"
                f"Sei ora cittadino #{citizen_id}.",
            )
            await send_log(
                context,
                f"✅ *Richiesta accettata* #{request_id}\n"
                f"{nominativo} è ora cittadino #{citizen_id} "
                f"(Telegram ID {riga['telegram_id']})\n"
                f"Gestita da: {admin_username}",
            )
            return

        repository.resolve_request(
            conn, request_id, repository.STATO_RIFIUTATA, admin.id, admin.username
        )

        await query.answer("Richiesta rifiutata.")
        testo_finale = (
            f"❌ Richiesta #{request_id} rifiutata da {admin_username}.\n{nominativo}"
        )
        await query.edit_message_text(testo_finale, reply_markup=InlineKeyboardMarkup([]))
        await aggiorna_copie_notifica(
            context, riga["notifiche"], testo_finale, salta=corrente
        )
        await avvisa_in_privato(
            context,
            riga["telegram_id"],
            "Purtroppo la tua richiesta di cittadinanza è stata rifiutata.",
        )
        await send_log(
            context,
            f"❌ *Richiesta rifiutata* #{request_id}\n"
            f"{nominativo} (Telegram ID {riga['telegram_id']})\n"
            f"Gestita da: {admin_username}",
        )
