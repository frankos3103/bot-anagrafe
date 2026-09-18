"""Registro dei comandi: unica fonte di verità per /help, /menu e il menu nativo.

Aggiungere un comando qui significa vederlo comparire automaticamente
nell'aiuto testuale, nella pulsantiera e (se pubblico) nel menu di Telegram.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .roles import Role
from .validators import (
    valida_nome,
    valida_ricerca,
    valida_riferimento_cittadino,
    valida_riferimento_utente,
    valida_telegram_id,
    valida_username_opzionale,
)


@dataclass(frozen=True)
class Campo:
    """Un passo del wizard di /menu."""

    chiave: str
    etichetta: str
    prompt: str
    validatore: Callable[[str], Any]
    opzionale: bool = False


@dataclass(frozen=True)
class Comando:
    nome: str
    ruolo: Role
    emoji: str
    descrizione: str
    uso: str
    esempio: str | None = None
    campi: tuple[Campo, ...] = ()
    etichetta_menu: str | None = None
    nel_menu: bool = True
    nell_help: bool = True
    nel_menu_telegram: bool = False

    @property
    def label(self) -> str:
        """Testo del pulsante nella pulsantiera."""
        return f"{self.emoji} {self.etichetta_menu or self.nome.capitalize()}"

    @property
    def richiede_input(self) -> bool:
        return bool(self.campi)


_CAMPO_NOME = Campo(
    "nome", "Nome", "Qual è il nome?", lambda v: valida_nome(v, "Il nome")
)
_CAMPO_COGNOME = Campo(
    "cognome", "Cognome", "Qual è il cognome?", lambda v: valida_nome(v, "Il cognome")
)


COMMANDS: tuple[Comando, ...] = (
    Comando(
        nome="start",
        ruolo=Role.PUBBLICO,
        emoji="👋",
        descrizione="Presentazione del bot",
        uso="/start",
        nel_menu=False,
        nell_help=False,
    ),
    Comando(
        nome="help",
        ruolo=Role.PUBBLICO,
        emoji="❓",
        descrizione="Elenco dei comandi disponibili per te",
        uso="/help",
        nel_menu=False,
        nel_menu_telegram=True,
    ),
    Comando(
        nome="menu",
        ruolo=Role.PUBBLICO,
        emoji="⌨️",
        descrizione="Apre la pulsantiera per eseguire i comandi senza digitarli",
        uso="/menu",
        nel_menu=False,
        nel_menu_telegram=True,
    ),
    Comando(
        nome="elenco",
        ruolo=Role.PUBBLICO,
        emoji="👥",
        descrizione="Elenco completo dei cittadini",
        uso="/elenco",
        etichetta_menu="Elenco",
        nel_menu_telegram=True,
    ),
    Comando(
        nome="esporta",
        ruolo=Role.PUBBLICO,
        emoji="📤",
        descrizione="Esporta il registro come file Markdown",
        uso="/esporta",
        etichetta_menu="Esporta",
        nel_menu_telegram=True,
    ),
    Comando(
        nome="cerca",
        ruolo=Role.PUBBLICO,
        emoji="🔍",
        descrizione="Cerca per nome e/o cognome, @username, #ID o ID Telegram",
        uso="/cerca <testo>",
        esempio="/cerca Mario Rossi",
        etichetta_menu="Cerca",
        campi=(
            Campo(
                "query",
                "Ricerca",
                "Cosa vuoi cercare? (nome e/o cognome, @username, #ID o ID Telegram)",
                valida_ricerca,
            ),
        ),
        nel_menu_telegram=True,
    ),
    Comando(
        nome="richiedi",
        ruolo=Role.PUBBLICO,
        emoji="📝",
        descrizione="Invia una richiesta di cittadinanza",
        uso="/richiedi <nome>, <cognome>",
        esempio="/richiedi Mario, Rossi",
        etichetta_menu="Richiedi",
        campi=(_CAMPO_NOME, _CAMPO_COGNOME),
        nel_menu_telegram=True,
    ),
    Comando(
        nome="inserisci",
        ruolo=Role.ADMIN,
        emoji="➕",
        descrizione="Inserisce un nuovo cittadino nel registro",
        uso="/inserisci <ID_telegram>, <username>, <nome>, <cognome>",
        esempio="/inserisci 123456789, @mariorossi, Mario, Rossi",
        etichetta_menu="Inserisci",
        campi=(
            Campo(
                "telegram_id",
                "ID Telegram",
                "Qual è l'ID Telegram del cittadino? (solo numeri)",
                valida_telegram_id,
            ),
            Campo(
                "username",
                "Username",
                "Qual è lo username? (senza @)",
                valida_username_opzionale,
                opzionale=True,
            ),
            _CAMPO_NOME,
            _CAMPO_COGNOME,
        ),
    ),
    Comando(
        nome="rimuovi",
        ruolo=Role.ADMIN,
        emoji="❌",
        descrizione="Rimuove un cittadino dal registro",
        uso="/rimuovi <ID_cittadino | ID_telegram | @username>",
        esempio="/rimuovi 12 oppure /rimuovi @mariorossi",
        etichetta_menu="Rimuovi",
        campi=(
            Campo(
                "cittadino",
                "Cittadino",
                "Quale cittadino vuoi rimuovere? (ID cittadino, ID Telegram "
                "oppure @username)",
                valida_riferimento_cittadino,
            ),
        ),
    ),
    Comando(
        nome="importa",
        ruolo=Role.ADMIN,
        emoji="📥",
        descrizione="Importa più cittadini da un file CSV",
        uso="/importa (allegando un file .csv)",
        esempio="invia il file .csv con didascalia /importa",
        etichetta_menu="Importa CSV",
    ),
    Comando(
        nome="elenco_admin",
        ruolo=Role.ROOT,
        emoji="👮",
        descrizione="Mostra gli amministratori configurati",
        uso="/elenco_admin",
        etichetta_menu="Elenco admin",
    ),
    Comando(
        nome="aggiungi_admin",
        ruolo=Role.ROOT,
        emoji="🛡",
        descrizione="Aggiunge un amministratore",
        uso="/aggiungi_admin <ID_telegram | @username>",
        esempio="/aggiungi_admin 123456789 oppure /aggiungi_admin @mariorossi",
        etichetta_menu="Aggiungi admin",
        campi=(
            Campo(
                "utente",
                "Utente",
                "Chi è il nuovo amministratore? (ID Telegram, oppure @username "
                "se è un cittadino)",
                valida_riferimento_utente,
            ),
        ),
    ),
    Comando(
        nome="rimuovi_admin",
        ruolo=Role.ROOT,
        emoji="🚫",
        descrizione="Rimuove un amministratore",
        uso="/rimuovi_admin <ID_telegram | @username>",
        esempio="/rimuovi_admin 123456789 oppure /rimuovi_admin @mariorossi",
        etichetta_menu="Rimuovi admin",
        campi=(
            Campo(
                "utente",
                "Utente",
                "Quale amministratore vuoi rimuovere? (ID Telegram, oppure "
                "@username se è un cittadino)",
                valida_riferimento_utente,
            ),
        ),
    ),
)


PER_NOME: dict[str, Comando] = {c.nome: c for c in COMMANDS}


def trova_comando(nome: str) -> Comando | None:
    return PER_NOME.get(nome)


def comandi_per_ruolo(ruolo: Role, solo_menu: bool = False) -> list[Comando]:
    """I comandi che quel ruolo può usare (un ruolo include quelli inferiori)."""
    return [
        c
        for c in COMMANDS
        if c.ruolo <= ruolo and (c.nel_menu if solo_menu else c.nell_help)
    ]


_TITOLI_SEZIONE = {
    Role.PUBBLICO: "Comandi disponibili",
    Role.ADMIN: "Comandi amministratore",
    Role.ROOT: "Comandi root (gestione amministratori)",
}


def render_help(ruolo: Role) -> str:
    """Testo dell'aiuto, con le sole sezioni a cui il ruolo ha accesso."""
    parti = ["🏛 Bot Registro Cittadini"]

    for sezione in (Role.PUBBLICO, Role.ADMIN, Role.ROOT):
        if sezione > ruolo:
            continue
        comandi = [c for c in comandi_per_ruolo(ruolo) if c.ruolo == sezione]
        if not comandi:
            continue
        parti.append("")
        parti.append(f"{_TITOLI_SEZIONE[sezione]}:")
        for c in comandi:
            parti.append(f"{c.emoji} {c.uso} — {c.descrizione}")

    parti.append("")
    parti.append("💡 Usa /menu per eseguire questi comandi con i pulsanti.")
    return "\n".join(parti)


def render_uso(comando: Comando) -> str:
    """Istruzioni d'uso di un singolo comando."""
    testo = f"{comando.emoji} {comando.descrizione}\n\nUso: {comando.uso}"
    if comando.esempio:
        testo += f"\nEsempio: {comando.esempio}"
    return testo


def comandi_menu_telegram() -> list[tuple[str, str]]:
    """Coppie (nome, descrizione) per set_my_commands: solo i comandi pubblici."""
    return [
        (c.nome, c.descrizione)
        for c in COMMANDS
        if c.nel_menu_telegram and c.ruolo == Role.PUBBLICO
    ]
