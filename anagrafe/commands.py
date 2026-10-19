"""Registro dei comandi: unica fonte di verità per /help, /menu e il menu nativo.

Aggiungere un comando qui significa vederlo comparire automaticamente
nell'aiuto testuale, nella pulsantiera e (se pubblico) nel menu di Telegram.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .roles import Role
from .validators import (
    valida_attivita_id,
    valida_contatto,
    valida_descrizione,
    valida_nome,
    valida_nome_attivita,
    valida_ricerca,
    valida_scelta,
    valida_riferimento_cittadino,
    valida_riferimento_utente,
    valida_telegram_id,
    valida_username_opzionale,
)


@dataclass(frozen=True)
class Sezione:
    """Un'area della pulsantiera: raggruppa i comandi per argomento.

    La sezione dice di che cosa si parla, il ruolo dice chi può agire: sono
    ortogonali, percio' i comandi riservati agli amministratori che riguardano
    i cittadini stanno in «Cittadinanza», non in «Amministrazione».
    """

    chiave: str
    etichetta: str
    emoji: str = ""

    @property
    def label(self) -> str:
        """Testo del pulsante nella vista principale."""
        return f"{self.emoji} {self.etichetta}".strip()


@dataclass(frozen=True)
class Opzione:
    """Una scelta a pulsante per un campo del wizard.

    `chiave` è il valore canonico che finisce nel database: è stabile nel tempo,
    così cambiare l'etichetta non invalida i dati già scritti. `etichetta` è il
    nome pubblico, quello che compare anche nelle schede della Gazzetta.
    """

    chiave: str
    etichetta: str
    emoji: str = ""

    @property
    def label(self) -> str:
        """Testo del pulsante."""
        return f"{self.emoji} {self.etichetta}".strip()


@dataclass(frozen=True)
class Campo:
    """Un passo del wizard di /menu."""

    chiave: str
    etichetta: str
    prompt: str
    validatore: Callable[[str], Any]
    opzionale: bool = False
    opzioni: tuple[Opzione, ...] = ()
    per_riga: int = 1
    # Chiave di un fornitore in handlers/scelte.py: le opzioni non sono fisse
    # ma lette dal registro quando il wizard arriva a questo campo, perché
    # dipendono dai dati e da chi sta chiedendo.
    scelte: str = ""
    # Cosa rispondere quando il fornitore non trova nulla da scegliere.
    messaggio_vuoto: str = ""

    @property
    def a_pulsanti(self) -> bool:
        """Il campo offre scelte fisse, dichiarate qui nel registro."""
        return bool(self.opzioni)

    @property
    def a_scelte(self) -> bool:
        """Il campo offre scelte lette dal registro al momento della domanda."""
        return bool(self.scelte)

    def mostra(self, valore: Any) -> str:
        """Il valore come va mostrato nel riepilogo: l'etichetta, non la chiave."""
        for opzione in self.opzioni:
            if opzione.chiave == valore:
                return opzione.label
        return "(nessuno)" if valore in (None, "") else str(valore)


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
    # L'area della pulsantiera in cui compare il pulsante. Vuota per i comandi
    # che non stanno nella pulsantiera (start, help, menu).
    sezione: str = ""
    nel_menu: bool = True
    nell_help: bool = True
    nel_menu_telegram: bool = False
    # Il comando entra subito nel proprio wizard, senza passare dalla
    # pulsantiera: va negli entry_points della ConversationHandler, non in
    # handlers.COMANDI. Vedi build_menu_handler().
    wizard_diretto: bool = False
    # Il comando si completa con un allegato invece che col wizard: vedi
    # avvia_wizard(). Dichiararlo qui evita di cablarne il nome negli handler.
    attende_allegato: bool = False
    # Raccolti i dati, esegue senza chiedere conferma. Per un export non c'è
    # nulla da confermare: il riepilogo sarebbe solo un click in più.
    senza_conferma: bool = False

    @property
    def label(self) -> str:
        """Testo del pulsante nella pulsantiera."""
        return f"{self.emoji} {self.etichetta_menu or self.nome.capitalize()}"

    @property
    def richiede_input(self) -> bool:
        return bool(self.campi)


SEZIONI: tuple[Sezione, ...] = (
    Sezione("cittadini", "Cittadinanza", "👥"),
    Sezione("attivita", "Attività", "🏪"),
    Sezione("amministrazione", "Amministrazione", "👮"),
)

SEZIONI_PER_CHIAVE: dict[str, Sezione] = {s.chiave: s for s in SEZIONI}


# Le tipologie previste dal Decreto Ministeriale n.3 del 13/10/2026. Unica
# fonte di verità: da qui nascono i pulsanti del wizard, il validatore del campo
# e le etichette delle schede pubblicate in Gazzetta.
TIPOLOGIE_ATTIVITA: tuple[Opzione, ...] = (
    Opzione("organizzazione", "Organizzazione", "🏢"),
    Opzione("associazione", "Associazione", "🤝"),
    Opzione("privata", "Attività Privata", "💼"),
)

ETICHETTE_TIPOLOGIA: dict[str, str] = {
    o.chiave: o.etichetta for o in TIPOLOGIE_ATTIVITA
}
EMOJI_TIPOLOGIA: dict[str, str] = {o.chiave: o.emoji for o in TIPOLOGIE_ATTIVITA}


# I formati in cui si può scaricare un registro. Il CSV è pensato per essere
# riletto dall'import: le intestazioni sono quelle che csv_import riconosce.
FORMATO_MD = "md"
FORMATO_CSV = "csv"

FORMATI_EXPORT: tuple[Opzione, ...] = (
    Opzione(FORMATO_MD, "Markdown", "📝"),
    Opzione(FORMATO_CSV, "CSV", "📊"),
)

ETICHETTE_FORMATO: dict[str, str] = {o.chiave: o.etichetta for o in FORMATI_EXPORT}


def etichetta_tipologia(chiave: str) -> str:
    """Il nome pubblico di una tipologia; la chiave grezza se è sconosciuta."""
    return ETICHETTE_TIPOLOGIA.get(chiave, str(chiave))


_CAMPO_FORMATO = Campo(
    "formato",
    "Formato",
    "In che formato vuoi il file?",
    lambda v: valida_scelta(v, ETICHETTE_FORMATO, "Il formato"),
    opzioni=FORMATI_EXPORT,
    per_riga=2,
)

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
        nome="elenco_cittadini",
        sezione="cittadini",
        ruolo=Role.PUBBLICO,
        emoji="👥",
        descrizione="Elenco completo dei cittadini",
        uso="/elenco_cittadini",
        etichetta_menu="Elenco",
        nel_menu_telegram=True,
    ),
    Comando(
        nome="esporta_cittadini",
        sezione="cittadini",
        ruolo=Role.PUBBLICO,
        emoji="📤",
        descrizione="Esporta il registro dei cittadini (Markdown o CSV)",
        uso="/esporta_cittadini [md | csv]",
        esempio="/esporta_cittadini csv",
        etichetta_menu="Esporta",
        campi=(_CAMPO_FORMATO,),
        senza_conferma=True,
        nel_menu_telegram=True,
    ),
    Comando(
        nome="cerca_cittadino",
        sezione="cittadini",
        ruolo=Role.PUBBLICO,
        emoji="🔍",
        descrizione="Cerca per nome e/o cognome, @username, #ID o ID Telegram",
        uso="/cerca_cittadino <testo>",
        esempio="/cerca_cittadino Mario Rossi",
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
        nome="richiedi_cittadinanza",
        sezione="cittadini",
        ruolo=Role.PUBBLICO,
        emoji="📝",
        descrizione="Invia una richiesta di cittadinanza",
        uso="/richiedi_cittadinanza <nome>, <cognome>",
        esempio="/richiedi_cittadinanza Mario, Rossi",
        etichetta_menu="Richiedi",
        campi=(_CAMPO_NOME, _CAMPO_COGNOME),
        nel_menu_telegram=True,
    ),
    Comando(
        nome="registra_attivita",
        sezione="attivita",
        ruolo=Role.PUBBLICO,
        emoji="🏪",
        descrizione="Iscrive una tua attività al Registro Pubblico delle Attività",
        uso="/registra_attivita",
        etichetta_menu="Registra",
        campi=(
            Campo(
                "nome_attivita",
                "Nome",
                "Come si chiama l'attività?",
                valida_nome_attivita,
            ),
            Campo(
                "tipologia",
                "Tipologia",
                "Di che tipo di attività si tratta?",
                lambda v: valida_scelta(v, ETICHETTE_TIPOLOGIA, "La tipologia"),
                opzioni=TIPOLOGIE_ATTIVITA,
            ),
            Campo(
                "descrizione",
                "Descrizione",
                "Descrivi l'attività in poche righe (massimo 500 caratteri).",
                valida_descrizione,
            ),
            Campo(
                "contatto_link",
                "Contatto",
                "Lascia un contatto o un link di riferimento "
                "(@username, https://..., un numero).",
                valida_contatto,
                opzionale=True,
            ),
        ),
        nel_menu_telegram=True,
        wizard_diretto=True,
    ),
    Comando(
        nome="elenco_attivita",
        sezione="attivita",
        ruolo=Role.PUBBLICO,
        emoji="📋",
        descrizione="Elenco delle attività iscritte al Registro Pubblico",
        uso="/elenco_attivita",
        etichetta_menu="Elenco",
        nel_menu_telegram=True,
    ),
    Comando(
        nome="rimuovi_attivita",
        sezione="attivita",
        # Pubblico perché il proprietario è un cittadino: qui il filtro non è il
        # ruolo ma la proprietà, verificata in controlli.verifica_attivita_rimovibile.
        ruolo=Role.PUBBLICO,
        emoji="🗑",
        descrizione="Ritira una tua attività dal Registro Pubblico",
        uso="/rimuovi_attivita <ID_attività>",
        esempio="/rimuovi_attivita 7",
        etichetta_menu="Rimuovi",
        campi=(
            Campo(
                "attivita",
                "Attività",
                "Quale attività vuoi rimuovere?",
                valida_attivita_id,
                scelte="attivita_rimovibili",
                messaggio_vuoto="Non hai attività attive da rimuovere.",
            ),
        ),
        nel_menu_telegram=True,
    ),
    Comando(
        nome="esporta_attivita",
        sezione="attivita",
        ruolo=Role.PUBBLICO,
        emoji="📤",
        descrizione="Esporta il Registro delle Attività (Markdown o CSV)",
        uso="/esporta_attivita [md | csv]",
        esempio="/esporta_attivita csv",
        etichetta_menu="Esporta",
        campi=(_CAMPO_FORMATO,),
        senza_conferma=True,
        nel_menu_telegram=True,
    ),
    Comando(
        nome="inserisci_cittadino",
        sezione="cittadini",
        ruolo=Role.ADMIN,
        emoji="➕",
        descrizione="Inserisce un nuovo cittadino nel registro",
        uso="/inserisci_cittadino <ID_telegram>, <username>, <nome>, <cognome>",
        esempio="/inserisci_cittadino 123456789, @mariorossi, Mario, Rossi",
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
        nome="rimuovi_cittadino",
        sezione="cittadini",
        ruolo=Role.ADMIN,
        emoji="❌",
        descrizione="Rimuove un cittadino dal registro",
        uso="/rimuovi_cittadino <ID_cittadino | ID_telegram | @username>",
        esempio="/rimuovi_cittadino 12 oppure /rimuovi_cittadino @mariorossi",
        etichetta_menu="Rimuovi",
        campi=(
            Campo(
                "cittadino",
                "Cittadino",
                "Quale cittadino vuoi rimuovere?",
                valida_riferimento_cittadino,
                scelte="cittadini",
                messaggio_vuoto="Il registro dei cittadini è vuoto.",
            ),
        ),
    ),
    Comando(
        nome="tagga_cittadini",
        sezione="cittadini",
        ruolo=Role.ADMIN,
        emoji="📣",
        descrizione="Tagga tutti i cittadini con uno username",
        uso="/tagga_cittadini",
        etichetta_menu="Tagga tutti",
    ),
    Comando(
        nome="importa_cittadini",
        sezione="cittadini",
        ruolo=Role.ADMIN,
        emoji="📥",
        attende_allegato=True,
        descrizione="Importa più cittadini da un file CSV",
        uso="/importa_cittadini (allegando un file .csv)",
        esempio="invia il file .csv con didascalia /importa_cittadini",
        etichetta_menu="Importa CSV",
    ),
    Comando(
        nome="importa_attivita",
        sezione="attivita",
        ruolo=Role.ADMIN,
        emoji="📥",
        descrizione="Importa più attività da un file CSV",
        uso="/importa_attivita (allegando un file .csv)",
        esempio="invia il file .csv con didascalia /importa_attivita",
        etichetta_menu="Importa CSV",
        attende_allegato=True,
    ),
    Comando(
        nome="modera_attivita",
        sezione="attivita",
        ruolo=Role.ADMIN,
        emoji="🏛",
        descrizione="Rimanda la scheda di un'attività con i pulsanti di moderazione",
        uso="/modera_attivita <ID_attività>",
        esempio="/modera_attivita 7",
        etichetta_menu="Modera",
        campi=(
            Campo(
                "attivita",
                "Attività",
                "Quale attività vuoi moderare?",
                valida_attivita_id,
                scelte="attivita_moderabili",
                messaggio_vuoto="Nessuna attività attiva nel Registro.",
            ),
        ),
    ),
    Comando(
        nome="elenco_admin",
        sezione="amministrazione",
        ruolo=Role.ROOT,
        emoji="👮",
        descrizione="Mostra gli amministratori configurati",
        uso="/elenco_admin",
        etichetta_menu="Elenco",
    ),
    Comando(
        nome="aggiungi_admin",
        sezione="amministrazione",
        ruolo=Role.ROOT,
        emoji="🛡",
        descrizione="Aggiunge un amministratore",
        uso="/aggiungi_admin <ID_telegram | @username>",
        esempio="/aggiungi_admin 123456789 oppure /aggiungi_admin @mariorossi",
        etichetta_menu="Aggiungi",
        campi=(
            Campo(
                "utente",
                "Utente",
                "Chi è il nuovo amministratore?",
                valida_riferimento_utente,
                scelte="cittadini",
                messaggio_vuoto="Il registro dei cittadini è vuoto.",
            ),
        ),
    ),
    Comando(
        nome="rimuovi_admin",
        sezione="amministrazione",
        ruolo=Role.ROOT,
        emoji="🚫",
        descrizione="Rimuove un amministratore",
        uso="/rimuovi_admin <ID_telegram | @username>",
        esempio="/rimuovi_admin 123456789 oppure /rimuovi_admin @mariorossi",
        etichetta_menu="Rimuovi",
        campi=(
            Campo(
                "utente",
                "Utente",
                "Quale amministratore vuoi rimuovere?",
                valida_riferimento_utente,
                scelte="amministratori",
                messaggio_vuoto="Non ci sono amministratori da rimuovere.",
            ),
        ),
    ),
)


PER_NOME: dict[str, Comando] = {c.nome: c for c in COMMANDS}


def trova_comando(nome: str) -> Comando | None:
    return PER_NOME.get(nome)


def comandi_per_ruolo(
    ruolo: Role, solo_menu: bool = False, sezione: str | None = None
) -> list[Comando]:
    """I comandi che quel ruolo può usare (un ruolo include quelli inferiori).

    Con `sezione` restituisce i soli comandi di quell'area della pulsantiera.
    """
    return [
        c
        for c in COMMANDS
        if c.ruolo <= ruolo
        and (c.nel_menu if solo_menu else c.nell_help)
        and (sezione is None or c.sezione == sezione)
    ]


def trova_sezione(chiave: str) -> Sezione | None:
    return SEZIONI_PER_CHIAVE.get(chiave)


def sezioni_per_ruolo(ruolo: Role) -> list[Sezione]:
    """Le sole sezioni che per quel ruolo hanno almeno un pulsante.

    Un cittadino non deve vedere «Amministrazione», e una sezione senza comandi
    visibili mostrerebbe una tastiera con il solo «Indietro».
    """
    return [
        sezione
        for sezione in SEZIONI
        if comandi_per_ruolo(ruolo, solo_menu=True, sezione=sezione.chiave)
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
