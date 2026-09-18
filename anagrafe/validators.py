"""Validazione e parsing degli argomenti dei comandi.

Queste funzioni non sanno nulla di Telegram: sono usate sia dai comandi testuali
(/inserisci ...) sia dal wizard di /menu sia dall'import CSV, così la stessa
regola non viene riscritta tre volte.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

LUNGHEZZA_MAX_NOME = 100
LUNGHEZZA_MAX_USERNAME = 32

# Telegram ammette solo lettere, cifre e underscore negli username.
USERNAME_VALIDO = re.compile(r"^[A-Za-z0-9_]+$")


class ErroreValidazione(ValueError):
    """Un valore fornito dall'utente non è accettabile. Il messaggio è mostrabile."""


def normalizza_username(valore: str | None) -> str | None:
    """Toglie la @ iniziale e gli spazi; un valore vuoto diventa None."""
    if valore is None:
        return None
    pulito = str(valore).strip().lstrip("@").strip()
    if not pulito or pulito == "-":
        return None
    if len(pulito) > LUNGHEZZA_MAX_USERNAME:
        raise ErroreValidazione(
            f"Lo username è troppo lungo (massimo {LUNGHEZZA_MAX_USERNAME} caratteri)."
        )
    if not USERNAME_VALIDO.match(pulito):
        raise ErroreValidazione(
            f"«{pulito}» non è uno username valido: sono ammesse solo lettere, "
            "cifre e underscore."
        )
    return pulito


def valida_telegram_id(valore: str | int) -> int:
    """Un ID Telegram è un intero positivo."""
    testo = str(valore).strip()
    if not testo:
        raise ErroreValidazione("L'ID Telegram non può essere vuoto.")
    try:
        numero = int(testo)
    except ValueError:
        raise ErroreValidazione(
            f"L'ID Telegram deve essere un numero intero, trovato «{testo}»."
        ) from None
    if numero <= 0:
        raise ErroreValidazione("L'ID Telegram deve essere un numero positivo.")
    return numero


def valida_citizen_id(valore: str | int) -> int:
    """Un ID cittadino è un intero positivo (accetta anche la forma #12)."""
    testo = str(valore).strip().lstrip("#").strip()
    if not testo:
        raise ErroreValidazione("L'ID cittadino non può essere vuoto.")
    try:
        numero = int(testo)
    except ValueError:
        raise ErroreValidazione(
            f"L'ID cittadino deve essere un numero intero, trovato «{testo}»."
        ) from None
    if numero <= 0:
        raise ErroreValidazione("L'ID cittadino deve essere un numero positivo.")
    return numero


def valida_nome(valore: str, etichetta: str = "Il nome") -> str:
    pulito = " ".join(str(valore).split())
    if not pulito:
        raise ErroreValidazione(f"{etichetta} non può essere vuoto.")
    if len(pulito) > LUNGHEZZA_MAX_NOME:
        raise ErroreValidazione(
            f"{etichetta} è troppo lungo (massimo {LUNGHEZZA_MAX_NOME} caratteri)."
        )
    return pulito


def valida_ricerca(valore: str) -> str:
    pulito = str(valore).strip()
    if len(pulito) < 2:
        raise ErroreValidazione("Inserisci almeno 2 caratteri da cercare.")
    return pulito


def valida_username_opzionale(valore: str) -> str | None:
    """Versione per il wizard: accetta anche il vuoto, che significa «nessuno»."""
    return normalizza_username(valore)


# Un cittadino si può indicare per ID cittadino (#12), per tag (@mario) o,
# dove ha senso, per ID Telegram.
RIF_CITIZEN_ID = "citizen_id"
RIF_TELEGRAM_ID = "telegram_id"
RIF_USERNAME = "username"


@dataclass(frozen=True)
class Riferimento:
    tipo: str
    valore: int | str

    def __str__(self) -> str:
        if self.tipo == RIF_USERNAME:
            return f"@{self.valore}"
        if self.tipo == RIF_CITIZEN_ID:
            return f"#{self.valore}"
        return str(self.valore)


def parse_riferimento(valore: str, default: str) -> Riferimento:
    """«@mario» -> tag, «#12» -> ID cittadino, «12» -> il tipo `default`."""
    testo = str(valore).strip()
    if not testo:
        raise ErroreValidazione("Indica un ID o un @username.")
    if testo.startswith("@"):
        username = normalizza_username(testo)
        if username is None:
            raise ErroreValidazione("Dopo la @ serve uno username.")
        return Riferimento(RIF_USERNAME, username)
    if testo.startswith("#"):
        return Riferimento(RIF_CITIZEN_ID, valida_citizen_id(testo))
    if default == RIF_CITIZEN_ID:
        return Riferimento(RIF_CITIZEN_ID, valida_citizen_id(testo))
    return Riferimento(RIF_TELEGRAM_ID, valida_telegram_id(testo))


def valida_riferimento_cittadino(valore: str) -> Riferimento:
    """Per /rimuovi: un numero nudo è un ID cittadino."""
    return parse_riferimento(valore, RIF_CITIZEN_ID)


def valida_riferimento_utente(valore: str) -> Riferimento:
    """Per i comandi admin: un numero nudo è un ID Telegram."""
    return parse_riferimento(valore, RIF_TELEGRAM_ID)


@dataclass(frozen=True)
class DatiCittadino:
    telegram_id: int
    username: str | None
    nome: str
    cognome: str


@dataclass(frozen=True)
class DatiRichiesta:
    nome: str
    cognome: str


def _campi_separati_da_virgola(raw: str, attesi: int) -> list[str]:
    """Le istruzioni d'uso le aggiunge chi chiama, leggendole dal registro comandi."""
    parti = [p.strip() for p in str(raw).split(",")]
    if len(parti) != attesi:
        raise ErroreValidazione(
            f"Formato non valido: servono esattamente {attesi} valori separati "
            f"da virgola (ne ho letti {len(parti)})."
        )
    return parti


def parse_inserisci(raw: str) -> DatiCittadino:
    """«123456789, @mariorossi, Mario, Rossi» -> DatiCittadino."""
    telegram_id_raw, username_raw, nome_raw, cognome_raw = _campi_separati_da_virgola(raw, 4)
    return DatiCittadino(
        telegram_id=valida_telegram_id(telegram_id_raw),
        username=normalizza_username(username_raw),
        nome=valida_nome(nome_raw, "Il nome"),
        cognome=valida_nome(cognome_raw, "Il cognome"),
    )


def parse_richiedi(raw: str) -> DatiRichiesta:
    """«Mario, Rossi» -> DatiRichiesta."""
    nome_raw, cognome_raw = _campi_separati_da_virgola(raw, 2)
    return DatiRichiesta(
        nome=valida_nome(nome_raw, "Il nome"),
        cognome=valida_nome(cognome_raw, "Il cognome"),
    )
