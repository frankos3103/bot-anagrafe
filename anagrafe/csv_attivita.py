"""Import del Registro delle Attività da file CSV.

Riusa le primitive di csv_import (decodifica, delimitatore, riconoscimento
dell'intestazione, righe scartate) e aggiunge il dialetto delle attività: le
colonne che riconosce, la risoluzione del proprietario e le regole del decreto.

Due regole non sono negoziabili, e sono le stesse dell'iscrizione singola:
il proprietario deve essere un cittadino iscritto all'anagrafe, e lo stesso
proprietario non può avere due attività attive con lo stesso nome. Le righe che
le violano vengono saltate con il motivo, non importate a metà.

L'import **non pubblica** nulla sulla Gazzetta Ciompista e non manda notifiche
agli amministratori: un file da cinquanta righe produrrebbe cinquanta post e
cinquanta messaggi a testa, e Telegram limita gli invii. Il resoconto lo dice
esplicitamente.
"""

from __future__ import annotations

import csv
import io
import sqlite3
from dataclasses import dataclass, field

from . import controlli, repository
from .commands import ETICHETTE_TIPOLOGIA
from .csv_import import (
    MAX_SCARTATE_MOSTRATE,
    RigaScartata,
    _delimitatore,
    _mappa_colonne_da,
    _riga_vuota,
    _valore,
    decodifica,
)
from .validators import (
    ErroreValidazione,
    normalizza_testo,
    valida_contatto,
    valida_descrizione,
    valida_nome_attivita,
    valida_riferimento_cittadino,
    valida_scelta,
)

# Le intestazioni scritte da esportazione.COLONNE_ATTIVITA, più gli alias
# ragionevoli. «ID attività» non è mappata: l'ID lo assegna il registro.
ALIAS_COLONNE = {
    "nome": "nome_attivita",
    "nomeattivita": "nome_attivita",
    "nomeattività": "nome_attivita",
    "attivita": "nome_attivita",
    "attività": "nome_attivita",
    "denominazione": "nome_attivita",
    "tipologia": "tipologia",
    "tipo": "tipologia",
    "categoria": "tipologia",
    "descrizione": "descrizione",
    "scopo": "descrizione",
    "contatto": "contatto_link",
    "contattolink": "contatto_link",
    "link": "contatto_link",
    "recapito": "contatto_link",
    "proprietario": "proprietario",
    "owner": "proprietario",
    "cittadino": "proprietario",
    "telegramid": "proprietario",
    "idtelegram": "proprietario",
}

COLONNE_OBBLIGATORIE = ("nome_attivita", "tipologia", "descrizione", "proprietario")
ORDINE_POSIZIONALE = (
    "nome_attivita",
    "tipologia",
    "descrizione",
    "contatto_link",
    "proprietario",
)


@dataclass(frozen=True)
class RigaAttivita:
    numero: int
    nome_attivita: str
    tipologia: str
    descrizione: str
    contatto_link: str | None
    proprietario: str  # come scritto nel file: si risolve all'import


@dataclass
class Parsing:
    righe: list[RigaAttivita] = field(default_factory=list)
    scartate: list[RigaScartata] = field(default_factory=list)
    intestazione_trovata: bool = False


@dataclass
class Esito:
    iscritte: list[tuple[int, RigaAttivita]] = field(default_factory=list)
    saltate: list[tuple[str, RigaAttivita]] = field(default_factory=list)
    scartate: list[RigaScartata] = field(default_factory=list)

    @property
    def totale_letto(self) -> int:
        return len(self.iscritte) + len(self.saltate) + len(self.scartate)


def parse_csv(testo: str) -> Parsing:
    """Legge il CSV e separa le righe valide da quelle da scartare.

    Qui si valida solo ciò che non richiede il registro: nome, tipologia,
    descrizione e contatto. Il proprietario resta come scritto, perché per
    risolverlo serve il database: lo fa importa_righe.
    """
    risultato = Parsing()
    if not testo.strip():
        return risultato

    lettore = csv.reader(io.StringIO(testo), delimiter=_delimitatore(testo))
    mappa: dict[str, int] | None = None
    visti: dict[tuple[str, str], int] = {}  # (proprietario, nome) -> prima riga

    for numero, riga in enumerate(lettore, start=1):
        if not riga or _riga_vuota(riga):
            continue

        if mappa is None:
            intestazione = _mappa_colonne_da(riga, ALIAS_COLONNE, COLONNE_OBBLIGATORIE)
            if intestazione is not None:
                mappa = intestazione
                risultato.intestazione_trovata = True
                continue
            mappa = {nome: i for i, nome in enumerate(ORDINE_POSIZIONALE)}

        grezzo = ", ".join(str(c).strip() for c in riga)
        try:
            nome = valida_nome_attivita(_valore(riga, mappa, "nome_attivita"))
            tipologia = valida_scelta(
                _valore(riga, mappa, "tipologia"), ETICHETTE_TIPOLOGIA, "La tipologia"
            )
            descrizione = valida_descrizione(_valore(riga, mappa, "descrizione"))
            contatto = valida_contatto(_valore(riga, mappa, "contatto_link"))
            proprietario = str(_valore(riga, mappa, "proprietario")).strip()
            if not proprietario:
                raise ErroreValidazione("Manca il proprietario.")
            # Si verifica subito che sia una forma riconoscibile: così un errore
            # di battitura non arriva fino al database.
            valida_riferimento_cittadino(proprietario)
        except ErroreValidazione as exc:
            risultato.scartate.append(RigaScartata(numero, str(exc), grezzo))
            continue

        impronta = (normalizza_testo(proprietario), normalizza_testo(nome))
        if impronta in visti:
            risultato.scartate.append(
                RigaScartata(
                    numero,
                    "Attività duplicata nel file "
                    f"(già alla riga {visti[impronta]}).",
                    grezzo,
                )
            )
            continue

        visti[impronta] = numero
        risultato.righe.append(
            RigaAttivita(
                numero=numero,
                nome_attivita=nome,
                tipologia=tipologia,
                descrizione=descrizione,
                contatto_link=contatto,
                proprietario=proprietario,
            )
        )

    return risultato


def importa_righe(conn: sqlite3.Connection, parsing: Parsing) -> Esito:
    """Iscrive le attività valide, saltando quelle che il decreto non ammette."""
    esito = Esito(scartate=list(parsing.scartate))

    for riga in parsing.righe:
        try:
            riferimento = valida_riferimento_cittadino(riga.proprietario)
            cittadino = controlli.risolvi_cittadino(conn, riferimento)
            owner_id = cittadino["telegram_id"]
            controlli.verifica_nome_attivita_libero(conn, owner_id, riga.nome_attivita)
        except ErroreValidazione as exc:
            esito.saltate.append((str(exc), riga))
            continue

        try:
            attivita_id = repository.create_attivita(
                conn,
                owner_id=owner_id,
                owner_username=cittadino["username"],
                nome_attivita=riga.nome_attivita,
                tipologia=riga.tipologia,
                descrizione=riga.descrizione,
                contatto_link=riga.contatto_link,
            )
        except sqlite3.IntegrityError:
            # L'indice unico parziale: ultima barriera sotto ai controlli.
            esito.saltate.append(("Nome già usato da questo proprietario.", riga))
        else:
            esito.iscritte.append((attivita_id, riga))

    return esito


def importa_da_bytes(conn: sqlite3.Connection, dati: bytes) -> Esito:
    """Scorciatoia: decodifica, analizza e importa in un colpo solo."""
    return importa_righe(conn, parse_csv(decodifica(dati)))


def render_esito(esito: Esito) -> str:
    """Resoconto leggibile da mandare in chat dopo un import."""
    parti = [
        "📥 Import attività completato",
        "",
        f"• Iscritte: {len(esito.iscritte)}",
        f"• Saltate: {len(esito.saltate)}",
        f"• Righe non valide: {len(esito.scartate)}",
    ]

    if esito.saltate:
        parti.append("")
        parti.append("Saltate:")
        for motivo, riga in esito.saltate[:MAX_SCARTATE_MOSTRATE]:
            parti.append(f"  riga {riga.numero} «{riga.nome_attivita}»: {motivo}")
        rimanenti = len(esito.saltate) - MAX_SCARTATE_MOSTRATE
        if rimanenti > 0:
            parti.append(f"  …e altre {rimanenti}.")

    if esito.scartate:
        parti.append("")
        parti.append("Righe non valide:")
        for scartata in esito.scartate[:MAX_SCARTATE_MOSTRATE]:
            parti.append(f"  riga {scartata.numero}: {scartata.motivo}")
        rimanenti = len(esito.scartate) - MAX_SCARTATE_MOSTRATE
        if rimanenti > 0:
            parti.append(f"  …e altre {rimanenti}.")

    if not esito.totale_letto:
        parti.append("")
        parti.append("⚠️ Il file non conteneva nessuna riga leggibile.")

    if esito.iscritte:
        parti.append("")
        parti.append(
            "ℹ️ Le attività importate non sono state pubblicate sulla Gazzetta "
            "Ciompista: un import di massa produrrebbe un post per riga."
        )

    return "\n".join(parti)
