#!/usr/bin/env python3
"""
Bot Telegram per la gestione del registro cittadini di una simulazione politica.

Comandi pubblici:
    /lista              - invia l'elenco di tutti i cittadini in formato Markdown
    /cerca <stringa>     - mostra i cittadini che contengono la stringa
                           nel nome, cognome o username
    /richiedi <nome>, <cognome>
                         - invia una richiesta di cittadinanza (ID e username
                           presi automaticamente dal profilo Telegram)

Comandi riservati agli amministratori (elencati in admins.txt):
    /inserisci <ID>, <username>, <nome>, <cognome>
                         - inserisce un nuovo cittadino (data automatica)
    /rimuovi <ID_cittadino>
                         - rimuove il cittadino con quell'ID cittadino

Le richieste di cittadinanza inviate con /richiedi vengono notificate nella
stessa chat con due pulsanti (Accetta / Rifiuta) che solo gli amministratori
possono usare.

Avvio:
    python3 bot.py
Richiede la variabile d'ambiente TELEGRAM_BOT_TOKEN (o la si può mettere
direttamente in fondo al file, vedi sezione __main__).
"""

import io
import logging
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
    InputFile,
)
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

# ----------------------------------------------------------------------
# Configurazione
# ----------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "registro.db"
ADMINS_PATH = BASE_DIR / "admins.txt"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Database
# ----------------------------------------------------------------------

def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Crea le tabelle cittadini e richieste se non esistono già."""
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cittadini (
                telegram_id     INTEGER NOT NULL,
                citizen_id      INTEGER PRIMARY KEY AUTOINCREMENT,
                username        TEXT,
                nome            TEXT NOT NULL,
                cognome         TEXT NOT NULL,
                data_acquisizione TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS richieste (
                request_id      INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id     INTEGER NOT NULL,
                username        TEXT,
                nome            TEXT NOT NULL,
                cognome         TEXT NOT NULL,
                data_richiesta  TEXT NOT NULL,
                stato           TEXT NOT NULL DEFAULT 'in_attesa',
                admin_id        INTEGER,
                admin_username  TEXT,
                data_gestione   TEXT
            )
            """
        )
        conn.commit()


def next_would_be_id_note() -> str:
    """Solo per chiarezza: citizen_id è AUTOINCREMENT, parte da 1."""
    return ""


# ----------------------------------------------------------------------
# Gestione amministratori
# ----------------------------------------------------------------------

def load_admin_ids() -> set[int]:
    """Legge admins.txt: un ID Telegram per riga. Righe vuote o che
    iniziano con # vengono ignorate."""
    if not ADMINS_PATH.exists():
        logger.warning("File admins.txt non trovato in %s", ADMINS_PATH)
        return set()

    ids = set()
    with open(ADMINS_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                ids.add(int(line))
            except ValueError:
                logger.warning("Riga non valida in admins.txt: %r", line)
    return ids


def is_admin(user_id: int) -> bool:
    return user_id in load_admin_ids()


# ----------------------------------------------------------------------
# Helper di formattazione
# ----------------------------------------------------------------------

def format_row(row: sqlite3.Row) -> str:
    username = f"@{row['username']}" if row["username"] else "(nessuno username)"
    return (
        f"#{row['citizen_id']} — {row['nome']} {row['cognome']} "
        f"({username}) — cittadino dal {row['data_acquisizione']}"
    )


# ----------------------------------------------------------------------
# Comandi pubblici
# ----------------------------------------------------------------------

def _md_escape(value: str) -> str:
    """Sfugge il carattere | (e i newline) per non rompere le tabelle Markdown."""
    if value is None:
        return ""
    return str(value).replace("|", "\\|").replace("\n", " ")


async def cmd_lista(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM cittadini ORDER BY citizen_id ASC"
        ).fetchall()

    if not rows:
        await update.message.reply_text("Il registro è vuoto.")
        return

    lines = [
        "# Registro Cittadini",
        "",
        f"Totale cittadini: {len(rows)}",
        "",
        "| ID cittadino | ID Telegram | Username | Nome | Cognome | Data acquisizione |",
        "|---|---|---|---|---|---|",
    ]
    for row in rows:
        username = f"@{row['username']}" if row["username"] else ""
        lines.append(
            "| {citizen_id} | {telegram_id} | {username} | {nome} | {cognome} | {data} |".format(
                citizen_id=row["citizen_id"],
                telegram_id=row["telegram_id"],
                username=_md_escape(username),
                nome=_md_escape(row["nome"]),
                cognome=_md_escape(row["cognome"]),
                data=row["data_acquisizione"],
            )
        )

    md_text = "\n".join(lines) + "\n"
    md_bytes = md_text.encode("utf-8")
    file_obj = io.BytesIO(md_bytes)
    file_obj.name = "registro_cittadini.md"

    await update.message.reply_document(
        document=InputFile(file_obj, filename="registro_cittadini.md"),
        caption=f"Registro cittadini — {len(rows)} cittadini totali.",
    )


async def cmd_cerca(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text(
            "Uso corretto: /cerca <stringa da cercare>"
        )
        return

    query = " ".join(context.args).strip()
    like_pattern = f"%{query}%"

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT * FROM cittadini
            WHERE nome LIKE ? COLLATE NOCASE
               OR cognome LIKE ? COLLATE NOCASE
               OR username LIKE ? COLLATE NOCASE
            ORDER BY citizen_id ASC
            """,
            (like_pattern, like_pattern, like_pattern),
        ).fetchall()

    if not rows:
        await update.message.reply_text(
            f"Nessun cittadino trovato per «{query}»."
        )
        return

    lines = [format_row(row) for row in rows]
    text = f"Risultati per «{query}» ({len(rows)}):\n\n" + "\n".join(lines)

    # Telegram limita i messaggi a 4096 caratteri: tronchiamo se serve
    if len(text) > 4000:
        text = text[:4000] + "\n\n[…elenco troncato, restringi la ricerca]"

    await update.message.reply_text(text)


# ----------------------------------------------------------------------
# Comandi amministratore
# ----------------------------------------------------------------------

async def cmd_inserisci(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text(
            "Non sei autorizzato a usare questo comando."
        )
        return

    # Il testo dopo il comando, es: "123456789, mariorossi, Mario, Rossi"
    raw_text = update.message.text.partition(" ")[2].strip()
    if not raw_text:
        await update.message.reply_text(
            "Uso corretto:\n/inserisci ID_telegram, username, nome, cognome\n\n"
            "Esempio:\n/inserisci 123456789, mariorossi, Mario, Rossi"
        )
        return

    parts = [p.strip() for p in raw_text.split(",")]
    if len(parts) != 4:
        await update.message.reply_text(
            "Formato non valido. Servono esattamente 4 valori separati da virgola:\n"
            "ID_telegram, username, nome, cognome"
        )
        return

    telegram_id_str, username, nome, cognome = parts

    if not telegram_id_str.isdigit():
        await update.message.reply_text(
            "L'ID Telegram deve essere un numero intero."
        )
        return

    telegram_id = int(telegram_id_str)
    username = username.lstrip("@") or None
    if not nome or not cognome:
        await update.message.reply_text("Nome e cognome non possono essere vuoti.")
        return

    data_acquisizione = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    with get_connection() as conn:
        # Evitiamo doppioni sullo stesso ID telegram
        existing = conn.execute(
            "SELECT citizen_id FROM cittadini WHERE telegram_id = ?", (telegram_id,)
        ).fetchone()
        if existing:
            await update.message.reply_text(
                f"Questo ID Telegram è già registrato come cittadino "
                f"#{existing['citizen_id']}."
            )
            return

        cursor = conn.execute(
            """
            INSERT INTO cittadini (telegram_id, username, nome, cognome, data_acquisizione)
            VALUES (?, ?, ?, ?, ?)
            """,
            (telegram_id, username, nome, cognome, data_acquisizione),
        )
        conn.commit()
        new_id = cursor.lastrowid

    conferma = (
        f"Cittadino inserito con successo!\n"
        f"ID cittadino: #{new_id}\n"
        f"Nome: {nome} {cognome}"
    )
    if username:
        conferma += f"\nUsername: @{username}"
    await update.message.reply_text(conferma)


async def cmd_rimuovi(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text(
            "Non sei autorizzato a usare questo comando."
        )
        return

    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text(
            "Uso corretto: /rimuovi <ID_cittadino>\nEsempio: /rimuovi 12"
        )
        return

    citizen_id = int(context.args[0])

    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM cittadini WHERE citizen_id = ?", (citizen_id,)
        ).fetchone()
        if not row:
            await update.message.reply_text(
                f"Nessun cittadino trovato con ID #{citizen_id}."
            )
            return

        conn.execute("DELETE FROM cittadini WHERE citizen_id = ?", (citizen_id,))
        conn.commit()

    await update.message.reply_text(
        f"Cittadino #{citizen_id} ({row['nome']} {row['cognome']}) rimosso dal registro."
    )


# ----------------------------------------------------------------------
# Comando di aiuto
# ----------------------------------------------------------------------

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "Bot del registro cittadini.\n\n"
        "Comandi disponibili per tutti:\n"
        "/lista — invia l'elenco completo in Markdown\n"
        "/cerca <testo> — cerca per nome, cognome o username\n"
        "/richiedi nome, cognome — invia una richiesta di cittadinanza\n\n"
        "Comandi amministratore:\n"
        "/inserisci ID, username, nome, cognome\n"
        "/rimuovi ID_cittadino"
    )
    await update.message.reply_text(text)


# ----------------------------------------------------------------------
# Richieste di cittadinanza
# ----------------------------------------------------------------------

async def cmd_richiedi(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    telegram_id = user.id
    username = user.username  # può essere None

    raw_text = update.message.text.partition(" ")[2].strip()
    if not raw_text:
        await update.message.reply_text(
            "Uso corretto: /richiedi <nome>, <cognome>\n\n"
            "Esempio: /richiedi Mario, Rossi"
        )
        return

    parts = [p.strip() for p in raw_text.split(",")]
    if len(parts) != 2 or not parts[0] or not parts[1]:
        await update.message.reply_text(
            "Formato non valido. Servono esattamente 2 valori separati da virgola:\n"
            "nome, cognome\n\nEsempio: /richiedi Mario, Rossi"
        )
        return

    nome, cognome = parts

    with get_connection() as conn:
        # Già cittadino?
        existing_citizen = conn.execute(
            "SELECT citizen_id FROM cittadini WHERE telegram_id = ?", (telegram_id,)
        ).fetchone()
        if existing_citizen:
            await update.message.reply_text(
                f"Sei già cittadino con ID #{existing_citizen['citizen_id']}."
            )
            return

        # Richiesta già in attesa?
        existing_request = conn.execute(
            "SELECT request_id FROM richieste WHERE telegram_id = ? AND stato = 'in_attesa'",
            (telegram_id,),
        ).fetchone()
        if existing_request:
            await update.message.reply_text(
                f"Hai già una richiesta in attesa (#{existing_request['request_id']}). "
                "Attendi che un amministratore la esamini."
            )
            return

        data_richiesta = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        cursor = conn.execute(
            """
            INSERT INTO richieste
                (telegram_id, username, nome, cognome, data_richiesta, stato)
            VALUES (?, ?, ?, ?, ?, 'in_attesa')
            """,
            (telegram_id, username, nome, cognome, data_richiesta),
        )
        conn.commit()
        request_id = cursor.lastrowid

    await update.message.reply_text(
        f"Richiesta di cittadinanza #{request_id} inviata! "
        "Un amministratore la esaminerà a breve."
    )

    richiedente = f"@{username}" if username else f"ID {telegram_id}"
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Accetta", callback_data=f"richiesta:accetta:{request_id}"),
                InlineKeyboardButton("❌ Rifiuta", callback_data=f"richiesta:rifiuta:{request_id}"),
            ]
        ]
    )
    await update.message.reply_text(
        f"📋 Nuova richiesta di cittadinanza #{request_id}\n"
        f"Da: {richiedente}\n"
        f"Nome: {nome} {cognome}\n\n"
        "Un amministratore può accettarla o rifiutarla con i pulsanti qui sotto.",
        reply_markup=keyboard,
    )


async def on_richiesta_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    clicking_user = query.from_user

    if not is_admin(clicking_user.id):
        await query.answer(
            "Non sei autorizzato a gestire le richieste.", show_alert=True
        )
        return

    try:
        _, azione, request_id_str = query.data.split(":")
        request_id = int(request_id_str)
    except (ValueError, AttributeError):
        await query.answer("Richiesta non valida.", show_alert=True)
        return

    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM richieste WHERE request_id = ?", (request_id,)
        ).fetchone()

        if not row:
            await query.answer("Richiesta non trovata.", show_alert=True)
            return

        if row["stato"] != "in_attesa":
            stato_leggibile = {
                "accettata": "già accettata",
                "rifiutata": "già rifiutata",
            }.get(row["stato"], row["stato"])
            await query.answer(f"Questa richiesta è {stato_leggibile}.", show_alert=True)
            return

        admin_username = f"@{clicking_user.username}" if clicking_user.username else clicking_user.full_name
        data_gestione = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        if azione == "accetta":
            # Doppio controllo: potrebbe essere già cittadino nel frattempo
            already_citizen = conn.execute(
                "SELECT citizen_id FROM cittadini WHERE telegram_id = ?",
                (row["telegram_id"],),
            ).fetchone()

            if already_citizen:
                conn.execute(
                    """
                    UPDATE richieste
                    SET stato = 'rifiutata', admin_id = ?, admin_username = ?, data_gestione = ?
                    WHERE request_id = ?
                    """,
                    (clicking_user.id, admin_username, data_gestione, request_id),
                )
                conn.commit()
                await query.answer(
                    "Questo utente è già cittadino, richiesta annullata.", show_alert=True
                )
                await query.edit_message_text(
                    f"⚠️ Richiesta #{request_id} annullata: {row['nome']} {row['cognome']} "
                    f"risultava già cittadino (#{already_citizen['citizen_id']})."
                )
                return

            cursor = conn.execute(
                """
                INSERT INTO cittadini (telegram_id, username, nome, cognome, data_acquisizione)
                VALUES (?, ?, ?, ?, ?)
                """,
                (row["telegram_id"], row["username"], row["nome"], row["cognome"], data_gestione),
            )
            new_citizen_id = cursor.lastrowid

            conn.execute(
                """
                UPDATE richieste
                SET stato = 'accettata', admin_id = ?, admin_username = ?, data_gestione = ?
                WHERE request_id = ?
                """,
                (clicking_user.id, admin_username, data_gestione, request_id),
            )
            conn.commit()

            await query.answer("Richiesta accettata!")
            await query.edit_message_text(
                f"✅ Richiesta #{request_id} accettata da {admin_username}.\n"
                f"{row['nome']} {row['cognome']} è ora cittadino #{new_citizen_id}."
            )

        elif azione == "rifiuta":
            conn.execute(
                """
                UPDATE richieste
                SET stato = 'rifiutata', admin_id = ?, admin_username = ?, data_gestione = ?
                WHERE request_id = ?
                """,
                (clicking_user.id, admin_username, data_gestione, request_id),
            )
            conn.commit()

            await query.answer("Richiesta rifiutata.")
            await query.edit_message_text(
                f"❌ Richiesta #{request_id} rifiutata da {admin_username}.\n"
                f"{row['nome']} {row['cognome']}"
            )

        else:
            await query.answer("Azione non riconosciuta.", show_alert=True)


# ----------------------------------------------------------------------
# Avvio applicazione
# ----------------------------------------------------------------------

def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    
    if not token:
        raise RuntimeError(
            "Imposta la variabile d'ambiente TELEGRAM_BOT_TOKEN con il token "
            "ottenuto da BotFather prima di avviare il bot."
        )

    init_db()

    application = Application.builder().token(token).build()

    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("lista", cmd_lista))
    application.add_handler(CommandHandler("cerca", cmd_cerca))
    application.add_handler(CommandHandler("richiedi", cmd_richiedi))
    application.add_handler(CommandHandler("inserisci", cmd_inserisci))
    application.add_handler(CommandHandler("rimuovi", cmd_rimuovi))
    application.add_handler(CallbackQueryHandler(on_richiesta_callback, pattern=r"^richiesta:"))

    logger.info("Bot avviato, in ascolto...")
    application.run_polling()


if __name__ == "__main__":
    main()