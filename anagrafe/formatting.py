"""Formattazione dei testi inviati su Telegram (escape, righe, impaginazione)."""

from __future__ import annotations

from typing import Iterable, Mapping, Sequence

from .commands import EMOJI_TIPOLOGIA, etichetta_tipologia

# Telegram rifiuta i messaggi oltre 4096 caratteri: teniamo un margine.
LIMITE_MESSAGGIO = 3800

CARATTERI_MARKDOWN_V2 = r"_*[]()~`>#+-=|{}.!"

# Telegram trasforma automaticamente "@username" in una menzione che notifica
# la persona, indipendentemente dal parse_mode. Uno spazio a larghezza zero
# subito dopo la @ è invisibile ma rompe il riconoscimento, così negli elenchi
# lo username si vede senza taggare nessuno.
SPAZIO_LARGHEZZA_ZERO = "​"


def escape_markdown_v2(valore: object) -> str:
    """Sfugge i caratteri speciali richiesti da Telegram in modalità MarkdownV2."""
    if valore is None:
        return ""
    testo = str(valore)
    for ch in CARATTERI_MARKDOWN_V2:
        testo = testo.replace(ch, "\\" + ch)
    return testo


# Il Markdown «legacy» usato da logbook.send_log riconosce solo questi quattro.
CARATTERI_MARKDOWN_LEGACY = "_*`["


def escape_markdown_legacy(valore: object) -> str:
    """Sfugge i caratteri del Markdown «legacy», quello di send_log.

    Senza questo, un nome come «Bar_Mario» farebbe fallire l'invio del log, e
    send_log non solleva: il messaggio si perderebbe in silenzio.
    """
    if valore is None:
        return ""
    testo = str(valore)
    for ch in CARATTERI_MARKDOWN_LEGACY:
        testo = testo.replace(ch, "\\" + ch)
    return testo


def escape_tabella(valore: object) -> str:
    """Sfugge il carattere | e i newline per non rompere le tabelle Markdown."""
    if valore is None:
        return ""
    return str(valore).replace("|", r"\|").replace("\n", " ")


def cognome_elenco(cognome: object) -> str:
    """Negli elenchi il cognome è sempre in maiuscolo, comunque sia stato scritto."""
    return str(cognome or "").upper()


def username_o_placeholder(username: str | None, placeholder: str = "(nessuno username)") -> str:
    """Tag vero e proprio (notifica l'utente): solo per /tagall."""
    return f"@{username}" if username else placeholder


def username_senza_tag(username: str | None, placeholder: str = "(nessuno username)") -> str:
    """Mostra lo username negli elenchi senza generare una menzione/notifica."""
    return f"@{SPAZIO_LARGHEZZA_ZERO}{username}" if username else placeholder


def format_row(row: Mapping) -> str:
    """Riga compatta usata da /cerca: «#3 — 12345 — Mario Rossi (@mariorossi)»."""
    # Il placeholder qui è senza parentesi: le mette la riga stessa.
    utente = username_senza_tag(row["username"], "nessuno username")
    return (
        f"#{row['citizen_id']} — {row['telegram_id']} — "
        f"{row['nome']} {cognome_elenco(row['cognome'])} ({utente})"
    )


def riga_elenco(row: Mapping) -> str:
    """Riga in MarkdownV2 usata da /elenco: «• *Mario Rossi* — @mariorossi»."""
    nome = escape_markdown_v2(row["nome"])
    cognome = escape_markdown_v2(cognome_elenco(row["cognome"]))
    if row["username"]:
        utente = f"@{SPAZIO_LARGHEZZA_ZERO}{escape_markdown_v2(row['username'])}"
    else:
        utente = r"_\(nessuno username\)_"
    return f"• *{nome} {cognome}* — {utente}"


def spezza_in_blocchi(
    righe: Sequence[str],
    intestazione: str | None = None,
    limite: int = LIMITE_MESSAGGIO,
) -> list[str]:
    """Raggruppa le righe in messaggi che stanno sotto il limite di Telegram.

    L'intestazione compare solo nel primo blocco. Una riga più lunga del limite
    viene troncata invece di far fallire l'invio.
    """
    blocchi: list[str] = []
    corrente: list[str] = []
    lunghezza = 0

    if intestazione:
        corrente.append(intestazione)
        lunghezza = len(intestazione) + 1

    for riga in righe:
        if len(riga) > limite:
            riga = riga[: limite - 1] + "…"
        if corrente and lunghezza + len(riga) + 1 > limite:
            blocchi.append("\n".join(corrente))
            corrente = []
            lunghezza = 0
        corrente.append(riga)
        lunghezza += len(riga) + 1

    if corrente:
        blocchi.append("\n".join(corrente))

    return blocchi


def tabella_markdown(righe: Iterable[Mapping], totale: int) -> str:
    """Documento Markdown completo prodotto da /esporta."""
    linee = [
        "# Registro Cittadini",
        "",
        f"Totale cittadini: {totale}",
        "",
        "| ID cittadino | ID Telegram | Username | Nome | Cognome |",
        "|---|---|---|---|---|",
    ]
    for row in righe:
        username = f"@{row['username']}" if row["username"] else ""
        linee.append(
            "| {cid} | {tid} | {username} | {nome} | {cognome} |".format(
                cid=row["citizen_id"],
                tid=row["telegram_id"],
                username=escape_tabella(username),
                nome=escape_tabella(row["nome"]),
                cognome=escape_tabella(cognome_elenco(row["cognome"])),
            )
        )
    return "\n".join(linee) + "\n"

# ----------------------------------------------------------------------
# Registro delle attività
# ----------------------------------------------------------------------

EMOJI_ATTIVITA = "🏪"


def _valore(row: Mapping, chiave: str):
    """Il campo se c'è, None se manca.

    Le schede si rendono anche da righe parziali, e sqlite3.Row alza IndexError
    invece di KeyError per una colonna assente.
    """
    try:
        return row[chiave]
    except (KeyError, IndexError):
        return None


def emoji_attivita(tipologia: str) -> str:
    return EMOJI_TIPOLOGIA.get(tipologia) or EMOJI_ATTIVITA


def contatto_visibile(
    contatto: str | None, placeholder: str = "(nessun contatto)"
) -> str:
    """Il contatto negli elenchi: un @tag non deve generare una menzione."""
    if not contatto:
        return placeholder
    if contatto.startswith("@"):
        return f"@{SPAZIO_LARGHEZZA_ZERO}{contatto[1:]}"
    return contatto


def riga_attivita(row: Mapping) -> str:
    """Riga in MarkdownV2 usata da /elenco_attivita."""
    nome = escape_markdown_v2(row["nome_attivita"])
    tipologia = escape_markdown_v2(etichetta_tipologia(row["tipologia"]))
    contatto = _valore(row, "contatto_link")
    if contatto:
        coda = escape_markdown_v2(contatto_visibile(contatto))
    else:
        coda = "_" + escape_markdown_v2("(nessun contatto)") + "_"
    return (
        f"• *{nome}* — {emoji_attivita(row['tipologia'])} {tipologia} — {coda}"
    )


def post_gazzetta(row: Mapping) -> str:
    """La scheda in MarkdownV2 pubblicata nella Gazzetta Ciompista.

    Ogni valore scritto dall'utente passa da escape_markdown_v2, e il contatto
    resta testo semplice invece di diventare un [testo](url): una URL fornita
    dall'utente dentro le parentesi di MarkdownV2 è un'iniezione, e un invio
    fallito su un canale passerebbe inosservato. Qui il tag è volutamente un tag
    vero: è il punto di una scheda pubblica.
    """
    righe = [
        "🏛 *Registro Pubblico delle Attività*",
        "",
        f"{emoji_attivita(row['tipologia'])} *{escape_markdown_v2(row['nome_attivita'])}*",
        f"🏷 {escape_markdown_v2(etichetta_tipologia(row['tipologia']))}",
        "",
        escape_markdown_v2(row["descrizione"]),
    ]
    contatto = _valore(row, "contatto_link")
    if contatto:
        righe += ["", f"📞 {escape_markdown_v2(contatto)}"]
    righe += [
        "",
        escape_markdown_v2(
            f"🆔 Attività #{row['attivita_id']} — iscritta il {row['created_at']}"
        ),
    ]
    return "\n".join(righe)


def post_gazzetta_rimosso(row: Mapping) -> str:
    """Sostituisce il post quando cancellarlo non è più possibile."""
    righe = [
        "➖ *Attività rimossa dal Registro*",
        "",
        f"~{escape_markdown_v2(row['nome_attivita'])}~ — "
        f"{escape_markdown_v2(etichetta_tipologia(row['tipologia']))}",
        "",
        escape_markdown_v2(
            "Rimossa d'ufficio dal Registro Pubblico delle Attività ai sensi "
            "del Decreto Ministeriale n.3 del 13/10/2026."
        ),
    ]
    return "\n".join(righe)


def scheda_moderazione(row: Mapping, cittadino: Mapping | None = None) -> str:
    """La scheda in chiaro inviata agli amministratori del Ministero.

    Va inviata senza parse_mode: così nessun carattere scritto dall'utente può
    far fallire l'invio della notifica di controllo. Se `cittadino` è None il
    proprietario non risulta più iscritto all'anagrafe, e il Ministero deve
    poterlo vedere.
    """
    if cittadino is not None:
        proprietario = (
            f"{username_senza_tag(cittadino['username'])} "
            f"(Telegram ID {row['owner_id']}) — cittadino #{cittadino['citizen_id']}"
        )
    else:
        proprietario = (
            f"{username_senza_tag(_valore(row, 'owner_username'))} "
            f"(Telegram ID {row['owner_id']}) — ⚠️ non risulta iscritto all'anagrafe"
        )

    righe = [
        f"🏛 Attività iscritta al Registro — #{row['attivita_id']}",
        "",
        f"🏪 Nome: {row['nome_attivita']}",
        f"🏷 Tipologia: {etichetta_tipologia(row['tipologia'])}",
        f"📝 {row['descrizione']}",
        f"📞 Contatto: {contatto_visibile(_valore(row, 'contatto_link'))}",
        "",
        f"Proprietario: {proprietario}",
        f"Iscritta il: {row['created_at']}",
    ]

    if _valore(row, "data_moderazione"):
        righe += [
            "",
            f"Stato: {row['stato']}",
            f"Moderata da: {username_senza_tag(_valore(row, 'admin_username'))} "
            f"(ID {_valore(row, 'admin_id')}) il {row['data_moderazione']}",
        ]
    else:
        righe += [
            "",
            "Ministero dell'Interno — Decreto Ministeriale n.3 del 13/10/2026.",
            "Se non è conforme puoi rifiutarla, oppure eliminarla dal Registro.",
        ]

    return "\n".join(righe)
