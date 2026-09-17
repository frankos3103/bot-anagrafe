"""Validazione e parsing degli argomenti dei comandi."""

import pytest

from anagrafe.validators import (
    ErroreValidazione,
    normalizza_username,
    parse_inserisci,
    parse_richiedi,
    valida_citizen_id,
    valida_nome,
    valida_ricerca,
    valida_telegram_id,
)


@pytest.mark.parametrize(
    "grezzo, atteso",
    [
        ("@mariorossi", "mariorossi"),
        ("mariorossi", "mariorossi"),
        ("  @mariorossi  ", "mariorossi"),
        ("", None),
        ("   ", None),
        ("-", None),
        (None, None),
    ],
)
def test_normalizza_username(grezzo, atteso):
    assert normalizza_username(grezzo) == atteso


def test_username_troppo_lungo():
    with pytest.raises(ErroreValidazione):
        normalizza_username("a" * 40)


@pytest.mark.parametrize("grezzo", ["non valido!!", "mario rossi", "mario-rossi", "ciao@tutti"])
def test_username_con_caratteri_non_ammessi(grezzo):
    """Telegram ammette solo lettere, cifre e underscore."""
    with pytest.raises(ErroreValidazione):
        normalizza_username(grezzo)


@pytest.mark.parametrize("grezzo", ["Mario_Rossi99", "mario", "_x_"])
def test_username_ammessi(grezzo):
    assert normalizza_username(grezzo) == grezzo


@pytest.mark.parametrize("grezzo", ["123456789", " 123456789 ", 123456789])
def test_telegram_id_valido(grezzo):
    assert valida_telegram_id(grezzo) == 123456789


@pytest.mark.parametrize("grezzo", ["", "abc", "12.5", "-5", "0"])
def test_telegram_id_non_valido(grezzo):
    with pytest.raises(ErroreValidazione):
        valida_telegram_id(grezzo)


def test_citizen_id_accetta_il_cancelletto():
    assert valida_citizen_id("#12") == 12
    assert valida_citizen_id("12") == 12


def test_nome_normalizza_gli_spazi():
    assert valida_nome("  Mario   Luigi  ") == "Mario Luigi"


def test_nome_vuoto():
    with pytest.raises(ErroreValidazione):
        valida_nome("   ")


def test_ricerca_troppo_corta():
    with pytest.raises(ErroreValidazione):
        valida_ricerca("a")


def test_parse_inserisci_completo():
    dati = parse_inserisci("123456789, @mariorossi, Mario, Rossi")
    assert dati.telegram_id == 123456789
    assert dati.username == "mariorossi"
    assert dati.nome == "Mario"
    assert dati.cognome == "Rossi"


def test_parse_inserisci_senza_username():
    dati = parse_inserisci("123456789, , Mario, Rossi")
    assert dati.username is None


@pytest.mark.parametrize(
    "grezzo",
    [
        "",
        "123456789, @mario, Mario",
        "123456789, @mario, Mario, Rossi, extra",
        "abc, @mario, Mario, Rossi",
        "123456789, @mario, , Rossi",
    ],
)
def test_parse_inserisci_non_valido(grezzo):
    with pytest.raises(ErroreValidazione):
        parse_inserisci(grezzo)


def test_parse_richiedi():
    dati = parse_richiedi("Mario, Rossi")
    assert (dati.nome, dati.cognome) == ("Mario", "Rossi")


@pytest.mark.parametrize("grezzo", ["", "Mario", "Mario, Rossi, Bianchi", "Mario, "])
def test_parse_richiedi_non_valido(grezzo):
    with pytest.raises(ErroreValidazione):
        parse_richiedi(grezzo)


def test_il_messaggio_di_errore_e_mostrabile():
    """I messaggi finiscono in chat: devono essere frasi in italiano."""
    with pytest.raises(ErroreValidazione) as info:
        valida_telegram_id("abc")
    assert "ID Telegram" in str(info.value)
