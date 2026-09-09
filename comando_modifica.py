# Campi modificabili con /modifica: alias accettati -> colonna reale in DB
CAMPI_MODIFICABILI = {
    "nome": "nome",
    "cognome": "cognome",
    "username": "username",
    "id": "telegram_id",
    "id_telegram": "telegram_id",
    "telegram_id": "telegram_id",
}


async def cmd_modifica(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text(
            "Non sei autorizzato a usare questo comando."
        )
        return

    # Testo dopo il comando, es: "21 cognome Di Marco"
    raw_text = update.message.text.partition(" ")[2].strip()
    if not raw_text:
        await update.message.reply_text(
            "Uso corretto: /modifica <ID_cittadino> <campo> <nuovo valore>\n\n"
            "Campi disponibili: nome, cognome, username, id (ID Telegram)\n\n"
            "Esempi:\n"
            "/modifica 13 username @nuovousername\n"
            "/modifica 21 cognome Di Marco\n"
            "/modifica 5 id 987654321"
        )
        return

    # maxsplit=2: separa ID, campo, e il resto (che può contenere spazi,
    # necessario per nomi/cognomi composti come "Di Marco")
    pezzi = raw_text.split(maxsplit=2)
    if len(pezzi) != 3:
        await update.message.reply_text(
            "Formato non valido. Uso corretto:\n"
            "/modifica <ID_cittadino> <campo> <nuovo valore>\n\n"
            "Esempio: /modifica 21 cognome Di Marco"
        )
        return

    citizen_id_str, campo_raw, nuovo_valore = pezzi

    if not citizen_id_str.isdigit():
        await update.message.reply_text("L'ID cittadino deve essere un numero intero.")
        return
    citizen_id = int(citizen_id_str)

    campo_key = campo_raw.strip().lower()
    if campo_key not in CAMPI_MODIFICABILI:
        campi_lista = ", ".join(sorted(set(CAMPI_MODIFICABILI.values())))
        await update.message.reply_text(
            f"Campo «{campo_raw}» non riconosciuto.\n"
            f"Campi disponibili: nome, cognome, username, id (ID Telegram)"
        )
        return
    colonna = CAMPI_MODIFICABILI[campo_key]

    nuovo_valore = nuovo_valore.strip()

    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM cittadini WHERE citizen_id = ?", (citizen_id,)
        ).fetchone()
        if not row:
            await update.message.reply_text(
                f"Nessun cittadino trovato con ID #{citizen_id}."
            )
            return

        # Validazioni specifiche per campo
        if colonna == "telegram_id":
            if not nuovo_valore.isdigit():
                await update.message.reply_text(
                    "Il nuovo ID Telegram deve essere un numero intero."
                )
                return
            nuovo_valore_db = int(nuovo_valore)

            # Evita di assegnare a due cittadini lo stesso ID Telegram
            duplicato = conn.execute(
                "SELECT citizen_id FROM cittadini WHERE telegram_id = ? AND citizen_id != ?",
                (nuovo_valore_db, citizen_id),
            ).fetchone()
            if duplicato:
                await update.message.reply_text(
                    f"Questo ID Telegram è già assegnato al cittadino "
                    f"#{duplicato['citizen_id']}."
                )
                return

        elif colonna == "username":
            pulito = nuovo_valore.lstrip("@").strip()
            # Permette di rimuovere l'username scrivendo "-"
            nuovo_valore_db = None if pulito in ("", "-") else pulito

        else:  # nome o cognome
            if not nuovo_valore:
                await update.message.reply_text(
                    f"Il nuovo {campo_key} non può essere vuoto."
                )
                return
            nuovo_valore_db = nuovo_valore

        valore_precedente = row[colonna]

        conn.execute(
            f"UPDATE cittadini SET {colonna} = ? WHERE citizen_id = ?",
            (nuovo_valore_db, citizen_id),
        )
        conn.commit()

    def fmt(v):
        if v is None:
            return "(nessuno)"
        if colonna == "username":
            return f"@{v}"
        return str(v)

    await update.message.reply_text(
        f"Cittadino #{citizen_id} aggiornato.\n"
        f"Campo: {campo_key}\n"
        f"Valore precedente: {fmt(valore_precedente)}\n"
        f"Nuovo valore: {fmt(nuovo_valore_db)}"
    )