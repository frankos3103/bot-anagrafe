"""Validazione e parsing degli argomenti dei comandi."""

import pytest

from anagrafe.validators import (
    RIF_CITIZEN_ID,
    RIF_NUMERO,
    RIF_TELEGRAM_ID,
    RIF_USERNAME,
    ErroreValidazione,
    Riferimento,
    normalizza_username,
    parse_inserisci,
    parse_richiedi,
    parse_riferimento,
    valida_attivita_id,
    valida_citizen_id,
    valida_contatto,
    valida_descrizione,
    valida_nome,
    valida_nome_attivita,
    valida_ricerca,
    valida_scelta,
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


@pytest.mark.parametrize(
    "grezzo, default, atteso",
    [
        ("@mariorossi", RIF_CITIZEN_ID, Riferimento(RIF_USERNAME, "mariorossi")),
        ("@mariorossi", RIF_TELEGRAM_ID, Riferimento(RIF_USERNAME, "mariorossi")),
        ("#12", RIF_TELEGRAM_ID, Riferimento(RIF_CITIZEN_ID, 12)),
        (" 12 ", RIF_CITIZEN_ID, Riferimento(RIF_CITIZEN_ID, 12)),
        (" 12 ", RIF_NUMERO, Riferimento(RIF_NUMERO, 12)),
        ("123456789", RIF_TELEGRAM_ID, Riferimento(RIF_TELEGRAM_ID, 123456789)),
    ],
)
def test_parse_riferimento(grezzo, default, atteso):
    assert parse_riferimento(grezzo, default) == atteso


@pytest.mark.parametrize("grezzo", ["", "@", "@non valido", "#abc", "mario", "-3"])
def test_parse_riferimento_non_valido(grezzo):
    with pytest.raises(ErroreValidazione):
        parse_riferimento(grezzo, RIF_TELEGRAM_ID)


def test_riferimento_leggibile():
    assert str(Riferimento(RIF_USERNAME, "mario")) == "@mario"
    assert str(Riferimento(RIF_CITIZEN_ID, 12)) == "#12"
    assert str(Riferimento(RIF_TELEGRAM_ID, 123)) == "123"


def test_il_messaggio_di_errore_e_mostrabile():
    """I messaggi finiscono in chat: devono essere frasi in italiano."""
    with pytest.raises(ErroreValidazione) as info:
        valida_telegram_id("abc")
    assert "ID Telegram" in str(info.value)


# ----------------------------------------------------------------------
# Registro delle attività
# ----------------------------------------------------------------------

TIPOLOGIE = {
    "organizzazione": "Organizzazione",
    "associazione": "Associazione",
    "privata": "Attività Privata",
}


@pytest.mark.parametrize(
    "scritto",
    [
        "privata",
        "Attività Privata",
        "attivita privata",
        "ATTIVITA  PRIVATA",
        "  attività privata  ",
        "💼 Attività Privata",
    ],
)
def test_una_scelta_si_riconosce_in_ogni_forma(scritto):
    """Chiave, etichetta, emoji, accenti e maiuscole portano tutte alla chiave."""
    assert valida_scelta(scritto, TIPOLOGIE, "La tipologia") == "privata"


def test_una_scelta_restituisce_sempre_la_chiave():
    for chiave, etichetta in TIPOLOGIE.items():
        assert valida_scelta(etichetta, TIPOLOGIE) == chiave


def test_una_scelta_ignota_elenca_le_ammesse():
    with pytest.raises(ErroreValidazione) as exc:
        valida_scelta("banca", TIPOLOGIE, "La tipologia")
    for etichetta in TIPOLOGIE.values():
        assert etichetta in str(exc.value)


@pytest.mark.parametrize("vuoto", ["", "   ", "💼"])
def test_una_scelta_vuota_e_rifiutata(vuoto):
    with pytest.raises(ErroreValidazione):
        valida_scelta(vuoto, TIPOLOGIE, "La tipologia")


def test_nome_attivita_su_una_riga_sola():
    assert valida_nome_attivita("  Pizzeria   Da\nMario ") == "Pizzeria Da Mario"


@pytest.mark.parametrize("brutto", ["", "   ", "x" * 81])
def test_nome_attivita_non_valido(brutto):
    with pytest.raises(ErroreValidazione):
        valida_nome_attivita(brutto)


def test_descrizione_conserva_i_capoversi():
    assert valida_descrizione(" Riga uno \n\n  Riga due ") == "Riga uno\n\nRiga due"


def test_descrizione_al_limite():
    assert len(valida_descrizione("x" * 500)) == 500


@pytest.mark.parametrize("brutta", ["", "   ", "x" * 501])
def test_descrizione_non_valida(brutta):
    with pytest.raises(ErroreValidazione):
        valida_descrizione(brutta)


@pytest.mark.parametrize("vuoto", ["", "   ", "-"])
def test_contatto_vuoto_significa_nessuno(vuoto):
    assert valida_contatto(vuoto) is None


@pytest.mark.parametrize(
    "buono", ["@pizzeria", "https://t.me/pizzeria", "https://sito.it", "+39 055 123456"]
)
def test_contatto_accettato(buono):
    assert valida_contatto(f"  {buono}  ") == buono


def test_contatto_su_piu_righe_e_rifiutato():
    """Spezzerebbe la riga del contatto nella scheda pubblicata in Gazzetta."""
    with pytest.raises(ErroreValidazione, match="una riga sola"):
        valida_contatto("@pizzeria\nhttps://spam.it")


def test_contatto_troppo_lungo():
    with pytest.raises(ErroreValidazione):
        valida_contatto("x" * 201)


@pytest.mark.parametrize("grezzo", ["7", "#7", " 7 ", " #7 "])
def test_id_attivita(grezzo):
    assert valida_attivita_id(grezzo) == 7


@pytest.mark.parametrize("brutto", ["", "abc", "0", "-3", "#"])
def test_id_attivita_non_valido(brutto):
    with pytest.raises(ErroreValidazione):
        valida_attivita_id(brutto)
