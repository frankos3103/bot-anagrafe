"""Formattazione dei messaggi: escape, righe e impaginazione."""

import pytest

from anagrafe.formatting import (
    LIMITE_MESSAGGIO,
    escape_markdown_v2,
    escape_tabella,
    format_row,
    riga_elenco,
    spezza_in_blocchi,
    tabella_markdown,
    username_o_placeholder,
)


def riga(citizen_id=1, telegram_id=111, username="mariorossi", nome="Mario", cognome="Rossi"):
    return {
        "citizen_id": citizen_id,
        "telegram_id": telegram_id,
        "username": username,
        "nome": nome,
        "cognome": cognome,
    }


def test_format_row_con_username():
    assert format_row(riga()) == "#1 — 111 — Mario ROSSI (@mariorossi)"


def test_format_row_senza_username():
    assert format_row(riga(username=None)) == "#1 — 111 — Mario ROSSI (nessuno username)"


def test_username_o_placeholder():
    assert username_o_placeholder("tizio") == "@tizio"
    assert username_o_placeholder(None) == "(nessuno username)"


@pytest.mark.parametrize(
    "grezzo, atteso",
    [
        ("Mario_Rossi", r"Mario\_Rossi"),
        ("D'Angelo-Neri", r"D'Angelo\-Neri"),
        ("100% (ok).", r"100% \(ok\)\."),
        (None, ""),
    ],
)
def test_escape_markdown_v2(grezzo, atteso):
    assert escape_markdown_v2(grezzo) == atteso


def test_escape_tabella():
    assert escape_tabella("a|b") == r"a\|b"
    assert escape_tabella("a\nb") == "a b"


@pytest.mark.parametrize("cognome", ["Zaccaria", "ZACCARIA", "zaccaria", "zAcCaRiA"])
def test_il_cognome_negli_elenchi_e_sempre_maiuscolo(cognome):
    dati = riga(nome="Giovanni", cognome=cognome)
    assert "*Giovanni ZACCARIA*" in riga_elenco(dati)
    assert "Giovanni ZACCARIA" in format_row(dati)
    assert "| Giovanni | ZACCARIA |" in tabella_markdown([dati], 1)


def test_cognome_accentato_in_maiuscolo():
    assert "ERÉSIA" in format_row(riga(cognome="Erésia"))


def test_riga_elenco_sfugge_i_caratteri_speciali():
    prodotta = riga_elenco(riga(nome="Gian_Luca", cognome="De-Rossi", username=None))
    assert r"Gian\_Luca" in prodotta
    assert r"DE\-ROSSI" in prodotta
    assert "nessuno username" in prodotta


# ----------------------------------------------------------------------
# Impaginazione
# ----------------------------------------------------------------------

def test_poche_righe_stanno_in_un_blocco():
    blocchi = spezza_in_blocchi(["a", "b", "c"], "Titolo")
    assert blocchi == ["Titolo\na\nb\nc"]


def test_nessuna_riga():
    assert spezza_in_blocchi([], "Titolo") == ["Titolo"]
    assert spezza_in_blocchi([]) == []


def test_molti_cittadini_vengono_spezzati():
    righe = [f"• Cittadino numero {i} con un nome piuttosto lungo" for i in range(500)]
    blocchi = spezza_in_blocchi(righe, "Titolo")

    assert len(blocchi) > 1
    assert all(len(b) <= LIMITE_MESSAGGIO for b in blocchi)

    # Nessuna riga persa e nessuna duplicata.
    ricomposto = "\n".join(blocchi).split("\n")
    assert ricomposto[0] == "Titolo"
    assert ricomposto[1:] == righe


def test_intestazione_solo_nel_primo_blocco():
    righe = [f"riga {i}" for i in range(500)]
    blocchi = spezza_in_blocchi(righe, "Titolo", limite=100)
    assert blocchi[0].startswith("Titolo")
    assert not any(b.startswith("Titolo") for b in blocchi[1:])


def test_riga_piu_lunga_del_limite_viene_troncata():
    blocchi = spezza_in_blocchi(["x" * 500], limite=100)
    assert len(blocchi) == 1
    assert len(blocchi[0]) <= 100
    assert blocchi[0].endswith("…")


# ----------------------------------------------------------------------
# Esportazione
# ----------------------------------------------------------------------

def test_tabella_markdown():
    testo = tabella_markdown([riga(), riga(2, 222, None, "Luigi", "Bianchi")], 2)
    assert "# Registro Cittadini" in testo
    assert "Totale cittadini: 2" in testo
    assert "| 1 | 111 | @mariorossi | Mario | ROSSI |" in testo
    assert "| 2 | 222 |  | Luigi | BIANCHI |" in testo
    assert testo.endswith("\n")


def test_tabella_markdown_sfugge_le_pipe():
    assert r"Mario\|Luigi" in tabella_markdown([riga(nome="Mario|Luigi")], 1)
