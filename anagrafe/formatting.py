"""Formattazione dei testi inviati su Telegram (escape, righe, impaginazione)."""

from __future__ import annotations

from typing import Iterable, Mapping, Sequence

# Telegram rifiuta i messaggi oltre 4096 caratteri: teniamo un margine.
LIMITE_MESSAGGIO = 3800

CARATTERI_MARKDOWN_V2 = r"_*[]()~`>#+-=|{}.!"


def escape_markdown_v2(valore: object) -> str:
    """Sfugge i caratteri speciali richiesti da Telegram in modalità MarkdownV2."""
    if valore is None:
        return ""
    testo = str(valore)
    for ch in CARATTERI_MARKDOWN_V2:
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
    return f"@{username}" if username else placeholder


def format_row(row: Mapping) -> str:
    """Riga compatta usata da /cerca: «#3 — 12345 — Mario Rossi (@mariorossi)»."""
    # Il placeholder qui è senza parentesi: le mette la riga stessa.
    utente = username_o_placeholder(row["username"], "nessuno username")
    return (
        f"#{row['citizen_id']} — {row['telegram_id']} — "
        f"{row['nome']} {cognome_elenco(row['cognome'])} ({utente})"
    )


def riga_elenco(row: Mapping) -> str:
    """Riga in MarkdownV2 usata da /elenco: «• *Mario Rossi* — @mariorossi»."""
    nome = escape_markdown_v2(row["nome"])
    cognome = escape_markdown_v2(cognome_elenco(row["cognome"]))
    if row["username"]:
        utente = f"@{escape_markdown_v2(row['username'])}"
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
