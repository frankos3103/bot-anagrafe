#!/usr/bin/env python3
"""
Bot Telegram per la gestione del registro cittadini di una simulazione politica.

Comandi pubblici:
    /esporta             - invia l'elenco di tutti i cittadini come file Markdown
    /elenco              - invia l'elenco di tutti i cittadini come messaggio
                           formattato (solo nome, cognome, username)
    /cerca <stringa>     - mostra i cittadini che contengono la stringa
                           nel nome, cognome o username
    /richiedi <nome>, <cognome>
                         - invia una richiesta di cittadinanza (ID e username
                           presi automaticamente dal profilo Telegram)

Comandi riservati agli amministratori:
    /inserisci <ID>, <username>, <nome>, <cognome>
                         - inserisce un nuovo cittadino (data automatica)
    /rimuovi <ID_cittadino>
                         - rimuove il cittadino con quell'ID cittadino

Comandi riservati al root:
    /aggiungi_admin <ID_telegram>
                         - aggiunge un amministratore
    /rimuovi_admin <ID_telegram>
                         - rimuove un amministratore
    /elenco_admin        - mostra gli amministratori configurati

Le richieste di cittadinanza inviate con /richiedi vengono notificate in
privato (messaggio diretto) a ciascun amministratore, con due pulsanti
(Accetta / Rifiuta). NOTA: perché un admin possa ricevere il messaggio
privato, deve aver avviato almeno una volta una chat con il bot (es.
premendo /start in privato) — è una limitazione di Telegram, non del bot.

Avvio:
    python3 bot.py
Richiede la variabile d'ambiente TOKEN (o la si può mettere
direttamente in fondo al file, vedi sezione __main__).
"""

import io
import json
import logging
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    Update,
    InputFile,
    BotCommand
)
from telegram.error import Forbidden, TelegramError
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters
)

# ----------------------------------------------------------------------
# Configurazione
# ----------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "registro.db"
ADMINS_PATH = BASE_DIR / "admins.txt"

# ID Telegram dell'utente root: può gestire l'elenco degli amministratori.
# Impostare la variabile d'ambiente ROOT_ADMIN_ID.
ROOT_ADMIN_ID = int(os.environ["ROOT_ADMIN_ID"])

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
                data_gestione   TEXT,
                notifiche       TEXT
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


def is_root(user_id: int) -> bool:
    return user_id == ROOT_ADMIN_ID


def is_admin(user_id: int) -> bool:
    # Il root è sempre admin, anche se non compare in admins.txt.
    return is_root(user_id) or user_id in load_admin_ids()


def add_admin_id(admin_id: int) -> bool:
    """Aggiunge un ID Telegram ad admins.txt.

    Restituisce True se l'ID è stato aggiunto, False se era già presente.
    """
    admin_ids = load_admin_ids()
    if admin_id in admin_ids:
        return False

    existing_lines = []
    if ADMINS_PATH.exists():
        existing_lines = ADMINS_PATH.read_text(encoding="utf-8").splitlines()

    with ADMINS_PATH.open("a", encoding="utf-8") as f:
        if existing_lines and not existing_lines[-1].endswith("\n"):
            # In pratica splitlines() rimuove il newline: aggiungiamo comunque
            # un newline prima del nuovo ID se il file non termina con uno.
            raw = ADMINS_PATH.read_text(encoding="utf-8")
            if raw and not raw.endswith("\n"):
                f.write("\n")
        f.write(f"{admin_id}\n")

    return True


def remove_admin_id(admin_id: int) -> bool:
    """Rimuove un ID Telegram da admins.txt.

    Restituisce True se l'ID è stato rimosso, False se non era presente.
    Il root non può essere rimosso.
    """
    if is_root(admin_id):
        return False

    if not ADMINS_PATH.exists():
        return False

    lines = ADMINS_PATH.read_text(encoding="utf-8").splitlines()
    found = False
    new_lines = []

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            new_lines.append(line)
            continue

        try:
            current_id = int(stripped)
        except ValueError:
            new_lines.append(line)
            continue

        if current_id == admin_id:
            found = True
            continue

        new_lines.append(line)

    if found:
        content = "\n".join(new_lines).rstrip("\n")
        if content:
            content += "\n"
        ADMINS_PATH.write_text(content, encoding="utf-8")

    return found


# ----------------------------------------------------------------------
# Helper di formattazione
# ----------------------------------------------------------------------

def format_row(row: sqlite3.Row) -> str:
    username = f"@{row['username']}" if row["username"] else "(nessuno username)"
    return (
        f"#{row['citizen_id']} — {row['telegram_id']} — {row['nome']} {row['cognome']} "
        f"({username})"
    )

# ----------------------------------------------------------------------
# Menù nativo di Telegram
# ----------------------------------------------------------------------

async def post_init(application: Application) -> None:
    # Definiamo i comandi pubblici visibili a tutti nel menu nativo di Telegram
    comandi_pubblici = [
        BotCommand("elenco", "Mostra l'elenco completo dei cittadini"),
        BotCommand("esporta", "Esporta il registro in formato Markdown"),
        BotCommand("cerca", "Cerca un cittadino per nome/cognome/username"),
        BotCommand("richiedi", "Richiedi la cittadinanza"),
        BotCommand("help", "Aiuto con i comandi"),
    ]
    # Imposta i comandi globalmente
    await application.bot.set_my_commands(comandi_pubblici)


# ----------------------------------------------------------------------
# Comandi pubblici
# ----------------------------------------------------------------------

def _md_escape(value: str) -> str:
    """Sfugge il carattere | (e i newline) per non rompere le tabelle Markdown."""
    if value is None:
        return ""
    return str(value).replace("|", "\\|").replace("\n", " ")


async def cmd_esporta(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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
        "| ID cittadino | ID Telegram | Username | Nome | Cognome |",
        "|---|---|---|---|---|",
    ]
    for row in rows:
        username = f"@{row['username']}" if row["username"] else ""
        lines.append(
            "| {citizen_id} | {telegram_id} | {username} | {nome} | {cognome} |".format(
                citizen_id=row["citizen_id"],
                telegram_id=row["telegram_id"],
                username=_md_escape(username),
                nome=_md_escape(row["nome"]),
                cognome=_md_escape(row["cognome"]),
                #data=row["data_acquisizione"],
            )
        )

    md_text = "\n".join(lines) + "\n"
    md_bytes = md_text.encode("utf-8")
    file_obj = io.BytesIO(md_bytes)
    file_obj.name = "registro_cittadini.md"

    await update.effective_message.reply_document(
        document=InputFile(file_obj, filename="registro_cittadini.md"),
        caption=f"Registro cittadini — {len(rows)} cittadini totali.",
    )


def _escape_markdown_v2(value: str) -> str:
    """Sfugge i caratteri speciali richiesti da Telegram in modalità MarkdownV2."""
    if value is None:
        return ""
    caratteri_speciali = r"_*[]()~`>#+-=|{}.!"
    testo = str(value)
    for ch in caratteri_speciali:
        testo = testo.replace(ch, f"\\{ch}")
    return testo


async def cmd_elenco(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM cittadini ORDER BY nome ASC, cognome ASC"
        ).fetchall()

    if not rows:
        await update.message.reply_text("Il registro è vuoto.")
        return

    righe_cittadini = []
    for row in rows:
        username = (
            f"@{_escape_markdown_v2(row['username'])}"
            if row["username"]
            else "_\\(nessuno username\\)_"
        )
        nome = _escape_markdown_v2(row["nome"])
        cognome = _escape_markdown_v2(row["cognome"])
        righe_cittadini.append(f"• *{nome} {cognome}* — {username}")

    intestazione = f"👥 *Elenco cittadini* \\({len(rows)}\\)"
    LIMITE = 3800  # margine di sicurezza sotto il limite di 4096 di Telegram

    blocchi = []
    blocco_corrente = [intestazione]
    lunghezza_corrente = len(intestazione)

    for riga in righe_cittadini:
        if lunghezza_corrente + len(riga) + 1 > LIMITE:
            blocchi.append("\n".join(blocco_corrente))
            blocco_corrente = []
            lunghezza_corrente = 0
        blocco_corrente.append(riga)
        lunghezza_corrente += len(riga) + 1

    if blocco_corrente:
        blocchi.append("\n".join(blocco_corrente))

    for blocco in blocchi:
        await update.effective_message.reply_text(blocco, parse_mode="MarkdownV2")


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

async def cmd_aggiungi_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id

    if not is_root(user_id):
        await update.message.reply_text(
            "Solo l'utente root può modificare l'elenco degli amministratori."
        )
        return

    if not context.args or not context.args[0].lstrip("-").isdigit():
        await update.message.reply_text(
            "Uso corretto: /aggiungi_admin <ID_telegram>\n"
            "Esempio: /aggiungi_admin 123456789"
        )
        return

    admin_id = int(context.args[0])

    if admin_id <= 0:
        await update.message.reply_text("L'ID Telegram deve essere positivo.")
        return

    if is_root(admin_id):
        await update.message.reply_text(
            "Questo ID è già il root e dispone automaticamente dei privilegi di amministratore."
        )
        return

    try:
        added = add_admin_id(admin_id)
    except OSError as exc:
        logger.exception("Errore aggiungendo l'admin %s", admin_id)
        await update.message.reply_text(
            f"Errore durante il salvataggio dell'amministratore: {exc}"
        )
        return

    if not added:
        await update.message.reply_text(
            f"L'ID Telegram {admin_id} è già un amministratore."
        )
        return

    await update.message.reply_text(
        f"✅ ID Telegram {admin_id} aggiunto agli amministratori."
    )


async def cmd_rimuovi_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id

    if not is_root(user_id):
        await update.message.reply_text(
            "Solo l'utente root può modificare l'elenco degli amministratori."
        )
        return

    if not context.args or not context.args[0].lstrip("-").isdigit():
        await update.message.reply_text(
            "Uso corretto: /rimuovi_admin <ID_telegram>\n"
            "Esempio: /rimuovi_admin 123456789"
        )
        return

    admin_id = int(context.args[0])

    if admin_id <= 0:
        await update.message.reply_text("L'ID Telegram deve essere positivo.")
        return

    if is_root(admin_id):
        await update.message.reply_text(
            "Il root non può essere rimosso dall'elenco degli amministratori."
        )
        return

    try:
        removed = remove_admin_id(admin_id)
    except OSError as exc:
        logger.exception("Errore rimuovendo l'admin %s", admin_id)
        await update.message.reply_text(
            f"Errore durante il salvataggio dell'elenco amministratori: {exc}"
        )
        return

    if not removed:
        await update.message.reply_text(
            f"L'ID Telegram {admin_id} non risulta nell'elenco degli amministratori."
        )
        return

    await update.message.reply_text(
        f"✅ ID Telegram {admin_id} rimosso dagli amministratori."
    )


async def cmd_elenco_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id

    if not is_root(user_id):
        await update.message.reply_text(
            "Solo l'utente root può visualizzare l'elenco degli amministratori."
        )
        return

    admin_ids = load_admin_ids()
    # Il root è sempre incluso, senza necessità di inserirlo in admins.txt.
    all_admin_ids = sorted(admin_ids | {ROOT_ADMIN_ID})

    if not all_admin_ids:
        await update.message.reply_text("Non ci sono amministratori configurati.")
        return

    righe = []
    for admin_id in all_admin_ids:
        ruolo = "root" if admin_id == ROOT_ADMIN_ID else "admin"
        righe.append(f"• {admin_id} — {ruolo}")

    await update.effective_message.reply_text(
        "👮 Elenco amministratori\n\n" + "\n".join(righe)
    )


async def cmd_inserisci(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text(
            "Non sei autorizzato a usare questo comando."
        )
        return

    # Il testo dopo il comando, es: "123456789, @mariorossi, Mario, Rossi"
    raw_text = update.message.text.partition(" ")[2].strip()
    if not raw_text:
        await update.message.reply_text(
            "Uso corretto:\n/inserisci ID_telegram, username, nome, cognome\n\n"
            "Esempio:\n/inserisci 123456789, @mariorossi, Mario, Rossi"
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
        "Comandi disponibili per tutti:\n\n" \
        "/help — mostra la pulsantiera dei comandi\n\n"
        "/esporta — invia l'elenco completo come file Markdown\n"
        "/elenco — invia l'elenco completo come messaggio (nome, cognome, username)\n"
        "/cerca <testo> — cerca per nome, cognome o username\n"
        "/richiedi nome, cognome — invia una richiesta di cittadinanza\n\n"
        "Comandi amministratore:\n"
        "/inserisci ID, username, nome, cognome\n"
        "/rimuovi ID_cittadino\n\n"
        "Comandi root (gestione amministratori):\n"
        "/aggiungi_admin ID_telegram\n"
        "/rimuovi_admin ID_telegram\n"
        "/elenco_admin"
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
    testo_notifica = (
        f"📋 Nuova richiesta di cittadinanza #{request_id}\n"
        f"Da: {richiedente}\n"
        f"Nome: {nome} {cognome}\n\n"
        "Puoi accettarla o rifiutarla con i pulsanti qui sotto."
    )

    admin_ids = load_admin_ids()
    if not admin_ids:
        logger.warning(
            "Nessun amministratore trovato in admins.txt: la richiesta #%s "
            "non è stata notificata a nessuno.",
            request_id,
        )

    admin_non_raggiungibili = []
    notifiche_inviate = []  # lista di [chat_id, message_id] per poterle aggiornare dopo
    for admin_id in admin_ids:
        try:
            sent_msg = await context.bot.send_message(
                chat_id=admin_id,
                text=testo_notifica,
                reply_markup=keyboard,
            )
            notifiche_inviate.append([sent_msg.chat_id, sent_msg.message_id])
        except Forbidden:
            # L'admin non ha mai avviato una chat privata con il bot
            admin_non_raggiungibili.append(admin_id)
            logger.warning(
                "Impossibile notificare l'admin %s: deve avviare prima una "
                "chat privata con il bot (/start).",
                admin_id,
            )
        except TelegramError as exc:
            admin_non_raggiungibili.append(admin_id)
            logger.warning("Errore inviando la notifica all'admin %s: %s", admin_id, exc)

    with get_connection() as conn:
        conn.execute(
            "UPDATE richieste SET notifiche = ? WHERE request_id = ?",
            (json.dumps(notifiche_inviate), request_id),
        )
        conn.commit()

    if admin_non_raggiungibili and update.effective_chat.type != "private":
        # Avvisa nella chat del gruppo che alcuni admin non sono raggiungibili,
        # così qualcuno può sollecitarli ad avviare il bot in privato.
        await update.message.reply_text(
            "⚠️ Attenzione: non sono riuscito a notificare in privato "
            f"{len(admin_non_raggiungibili)} amministratore/i. Devono prima "
            "avviare una chat privata con il bot (premendo /start in privato) "
            "per poter ricevere le notifiche delle richieste."
        )


async def _aggiorna_notifiche_admin(
    context: ContextTypes.DEFAULT_TYPE,
    notifiche_json: str | None,
    testo_finale: str,
    skip_chat_message: tuple[int, int] | None = None,
) -> None:
    """Aggiorna (o rimuove i pulsanti da) tutti i messaggi di notifica inviati
    agli admin per una richiesta, così tutti vedono l'esito e non solo chi ha
    cliccato. skip_chat_message evita di modificare due volte lo stesso
    messaggio se è già stato aggiornato con edit_message_text sulla query."""
    if not notifiche_json:
        return
    try:
        notifiche = json.loads(notifiche_json)
    except (ValueError, TypeError):
        return

    for chat_id, message_id in notifiche:
        if skip_chat_message and (chat_id, message_id) == skip_chat_message:
            continue
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=testo_finale,
                reply_markup=InlineKeyboardMarkup([]),
            )
        except TelegramError as exc:
            logger.warning(
                "Impossibile aggiornare la notifica in chat %s (msg %s): %s",
                chat_id, message_id, exc,
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
        current_chat_msg = (query.message.chat_id, query.message.message_id)

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
                testo_finale = (
                    f"⚠️ Richiesta #{request_id} annullata: {row['nome']} {row['cognome']} "
                    f"risultava già cittadino (#{already_citizen['citizen_id']})."
                )
                await query.edit_message_text(testo_finale, reply_markup=InlineKeyboardMarkup([]))
                await _aggiorna_notifiche_admin(
                    context, row["notifiche"], testo_finale, skip_chat_message=current_chat_msg
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
            testo_finale = (
                f"✅ Richiesta #{request_id} accettata da {admin_username}.\n"
                f"{row['nome']} {row['cognome']} è ora cittadino #{new_citizen_id}."
            )
            await query.edit_message_text(testo_finale, reply_markup=InlineKeyboardMarkup([]))
            await _aggiorna_notifiche_admin(
                context, row["notifiche"], testo_finale, skip_chat_message=current_chat_msg
            )

            # Avvisa anche il richiedente, se possibile
            try:
                await context.bot.send_message(
                    chat_id=row["telegram_id"],
                    text=(
                        f"🎉 La tua richiesta di cittadinanza è stata accettata!\n"
                        f"Sei ora cittadino #{new_citizen_id}."
                    ),
                )
            except TelegramError:
                pass

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
            testo_finale = (
                f"❌ Richiesta #{request_id} rifiutata da {admin_username}.\n"
                f"{row['nome']} {row['cognome']}"
            )
            await query.edit_message_text(testo_finale, reply_markup=InlineKeyboardMarkup([]))
            await _aggiorna_notifiche_admin(
                context, row["notifiche"], testo_finale, skip_chat_message=current_chat_msg
            )

            # Avvisa anche il richiedente, se possibile
            try:
                await context.bot.send_message(
                    chat_id=row["telegram_id"],
                    text="Purtroppo la tua richiesta di cittadinanza è stata rifiutata.",
                )
            except TelegramError:
                pass

        else:
            await query.answer("Azione non riconosciuta.", show_alert=True)


# ----------------------------------------------------------------------
# Comando /help con pulsantiera inline
# ----------------------------------------------------------------------

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id

    # Comandi pubblici per tutti
    keyboard = [
        [
            InlineKeyboardButton("👥 Elenco", callback_data="cmd_btn:elenco"),
            InlineKeyboardButton("📥 Esporta", callback_data="cmd_btn:esporta"),
        ],
        [
            InlineKeyboardButton("🔍 Cerca", callback_data="cmd_btn:cerca"),
            InlineKeyboardButton("📝 Richiedi", callback_data="cmd_btn:richiedi"),
        ],
    ]

    # Comandi per Amministratori
    if is_admin(user_id):
        keyboard.append([
            InlineKeyboardButton("➕ Inserisci", callback_data="cmd_btn:inserisci"),
            InlineKeyboardButton("❌ Rimuovi", callback_data="cmd_btn:rimuovi"),
        ])

    # Comandi per Root
    if is_root(user_id):
        keyboard.append([
            InlineKeyboardButton("👮 Elenco Admin", callback_data="cmd_btn:elenco_admin"),
        ])
        keyboard.append([
            InlineKeyboardButton("➕ Aggiungi Admin", callback_data="cmd_btn:aggiungi_admin"),
            InlineKeyboardButton("➖ Rimuovi Admin", callback_data="cmd_btn:rimuovi_admin"),
        ])

    reply_markup = InlineKeyboardMarkup(keyboard)

    text = (
        "🏛 *Bot Registro Cittadini — Menu Comandi*\n\n"
        "Seleziona un comando qui sotto per eseguirlo subito o per vedere le istruzioni di utilizzo:"
    )

    await update.effective_message.reply_text(
        text, reply_markup=reply_markup, parse_mode="Markdown"
    )


async def on_cmd_button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Gestisce la pressione dei pulsanti della tastiera del comando /help."""
    query = update.callback_query
    await query.answer()

    cmd = query.data.split(":")[1]
    user_id = query.from_user.id

    # Controlli sicurezza permessi
    if cmd in ("inserisci", "rimuovi") and not is_admin(user_id):
        await query.message.reply_text("⛔ Non sei autorizzato a usare questo comando.")
        return
    if cmd in ("elenco_admin", "aggiungi_admin", "rimuovi_admin") and not is_root(user_id):
        await query.message.reply_text("⛔ Comando riservato all'utente root.")
        return

    # Esecuzione immediata per comandi senza parametri
    if cmd == "elenco":
        await cmd_elenco(update, context)
    elif cmd == "esporta":
        await cmd_esporta(update, context)
    elif cmd == "elenco_admin":
        await cmd_elenco_admin(update, context)

    # Istruzioni d'uso per comandi che richiedono parametri
    elif cmd == "cerca":
        await query.message.reply_text("🔍 *Uso del comando:*\n`/cerca <stringa>`\n\n_Esempio:_ `/cerca Mario`", parse_mode="Markdown")
    elif cmd == "richiedi":
        await query.message.reply_text("📝 *Uso del comando:*\n`/richiedi <nome>, <cognome>`\n\n_Esempio:_ `/richiedi Mario, Rossi`", parse_mode="Markdown")
    elif cmd == "inserisci":
        await query.message.reply_text("➕ *Uso del comando:*\n`/inserisci ID_telegram, username, nome, cognome`\n\n_Esempio:_ `/inserisci 123456789, @mariorossi, Mario, Rossi`", parse_mode="Markdown")
    elif cmd == "rimuovi":
        await query.message.reply_text("❌ *Uso del comando:*\n`/rimuovi <ID_cittadino>`\n\n_Esempio:_ `/rimuovi 12`", parse_mode="Markdown")
    elif cmd == "aggiungi_admin":
        await query.message.reply_text("➕ *Uso del comando:*\n`/aggiungi_admin <ID_telegram>`", parse_mode="Markdown")
    elif cmd == "rimuovi_admin":
        await query.message.reply_text("➖ *Uso del comando:*\n`/rimuovi_admin <ID_telegram>`", parse_mode="Markdown")

# ----------------------------------------------------------------------
# Avvio applicazione
# ----------------------------------------------------------------------

def main() -> None:
    token = os.environ.get("TOKEN")
    if not token:
        raise RuntimeError(
            "Imposta la variabile d'ambiente TOKEN con il token "
            "ottenuto da BotFather prima di avviare il bot."
        )

    init_db()

    application = Application.builder().token(token).post_init(post_init).build()

    # 1. Comandi specifici
    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("help", cmd_help))
    application.add_handler(CommandHandler("esporta", cmd_esporta))
    application.add_handler(CommandHandler("elenco", cmd_elenco))
    application.add_handler(CommandHandler("cerca", cmd_cerca))
    application.add_handler(CommandHandler("richiedi", cmd_richiedi))
    application.add_handler(CommandHandler("inserisci", cmd_inserisci))
    application.add_handler(CommandHandler("rimuovi", cmd_rimuovi))
    application.add_handler(CommandHandler("aggiungi_admin", cmd_aggiungi_admin))
    application.add_handler(CommandHandler("rimuovi_admin", cmd_rimuovi_admin))
    application.add_handler(CommandHandler("elenco_admin", cmd_elenco_admin))

    # 2. Callback handlers
    application.add_handler(CallbackQueryHandler(on_richiesta_callback, pattern=r"^richiesta:"))
    application.add_handler(CallbackQueryHandler(on_cmd_button_callback, pattern=r"^cmd_btn:")) 

    # 3. HANDLER CATCH-ALL
    application.add_handler(MessageHandler(filters.TEXT | filters.COMMAND, cmd_help))
    

    logger.info("Bot avviato, in ascolto...")
    application.run_polling()


if __name__ == "__main__":
    main()