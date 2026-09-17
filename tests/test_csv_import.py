"""Parsing e import di file CSV."""

import pytest

from anagrafe import repository
from anagrafe.csv_import import (
    decodifica,
    importa_da_bytes,
    importa_righe,
    parse_csv,
    render_esito,
)

INTESTATO = """Telegram ID,Username,Nome,Cognome
111,@mariorossi,Mario,Rossi
222,@lbianchi,Luigi,Bianchi
"""


def test_intestazione_riconosciuta():
    parsing = parse_csv(INTESTATO)
    assert parsing.intestazione_trovata is True
    assert [r.telegram_id for r in parsing.righe] == [111, 222]
    assert parsing.righe[0].username == "mariorossi"
    assert not parsing.scartate


def test_alias_delle_colonne():
    testo = "id,utente,first name,last name\n111,mario,Mario,Rossi\n"
    parsing = parse_csv(testo)
    assert parsing.intestazione_trovata is True
    assert parsing.righe[0].nome == "Mario"
    assert parsing.righe[0].cognome == "Rossi"


def test_colonne_in_ordine_diverso():
    testo = "Cognome,Nome,Telegram ID,Username\nRossi,Mario,111,@mariorossi\n"
    riga = parse_csv(testo).righe[0]
    assert (riga.telegram_id, riga.nome, riga.cognome) == (111, "Mario", "Rossi")


def test_senza_intestazione_ordine_posizionale():
    parsing = parse_csv("111,@mariorossi,Mario,Rossi\n")
    assert parsing.intestazione_trovata is False
    assert parsing.righe[0].nome == "Mario"


def test_riga_spazzatura_iniziale_ignorata():
    """I fogli di calcolo esportano spesso una prima riga vuota tipo «,,,»."""
    parsing = parse_csv(",,,\n" + INTESTATO)
    assert parsing.intestazione_trovata is True
    assert len(parsing.righe) == 2
    assert not parsing.scartate


def test_righe_vuote_in_mezzo_ignorate():
    parsing = parse_csv(INTESTATO + "\n\n")
    assert len(parsing.righe) == 2
    assert not parsing.scartate


def test_punto_e_virgola():
    parsing = parse_csv("Telegram ID;Username;Nome;Cognome\n111;@mario;Mario;Rossi\n")
    assert parsing.righe[0].telegram_id == 111


def test_bom_utf8():
    assert decodifica(INTESTATO.encode("utf-8-sig")).startswith("Telegram ID")


def test_accenti_in_cp1252():
    testo = decodifica("Telegram ID,Username,Nome,Cognome\n111,,Niccolò,Erésia\n".encode("cp1252"))
    assert parse_csv(testo).righe[0].nome == "Niccolò"


def test_file_vuoto():
    parsing = parse_csv("")
    assert parsing.righe == [] and parsing.scartate == []


def test_riga_non_valida_scartata_con_motivo():
    parsing = parse_csv(INTESTATO + "abc,@tizio,Tizio,Caio\n")
    assert len(parsing.righe) == 2
    assert len(parsing.scartate) == 1
    scartata = parsing.scartate[0]
    assert scartata.numero == 4  # 1 intestazione + 2 righe buone
    assert "ID Telegram" in scartata.motivo
    assert "Tizio" in scartata.contenuto


def test_id_mancante_scartato():
    parsing = parse_csv(INTESTATO + ", , Mark, Freccia\n")
    assert len(parsing.scartate) == 1


def test_nome_mancante_scartato():
    parsing = parse_csv(INTESTATO + "333,@tizio,,Caio\n")
    assert len(parsing.scartate) == 1
    assert "nome" in parsing.scartate[0].motivo.lower()


def test_username_non_valido_scartato():
    parsing = parse_csv(INTESTATO + "333,mario rossi,Tizio,Caio\n")
    assert len(parsing.scartate) == 1
    assert "username" in parsing.scartate[0].motivo.lower()


def test_duplicato_interno_al_file():
    parsing = parse_csv(INTESTATO + "111,@altro,Mario,Rossi\n")
    assert len(parsing.righe) == 2
    assert len(parsing.scartate) == 1
    assert "duplicato" in parsing.scartate[0].motivo.lower()
    assert "riga 2" in parsing.scartate[0].motivo


# ----------------------------------------------------------------------
# Scrittura sul registro
# ----------------------------------------------------------------------

def test_import_inserisce(conn):
    esito = importa_righe(conn, parse_csv(INTESTATO))
    assert len(esito.inseriti) == 2
    assert not esito.saltati
    assert repository.count_citizens(conn) == 2


def test_reimport_salta_i_gia_presenti(conn):
    importa_righe(conn, parse_csv(INTESTATO))
    esito = importa_righe(conn, parse_csv(INTESTATO))
    assert not esito.inseriti
    assert len(esito.saltati) == 2
    assert repository.count_citizens(conn) == 2  # nessun doppione


def test_import_parziale(conn):
    repository.insert_citizen(conn, 111, "@mariorossi", "Mario", "Rossi")
    esito = importa_righe(conn, parse_csv(INTESTATO))
    assert len(esito.inseriti) == 1
    assert len(esito.saltati) == 1
    assert esito.inseriti[0][1].telegram_id == 222


def test_le_scartate_arrivano_fino_allesito(conn):
    esito = importa_righe(conn, parse_csv(INTESTATO + "abc,,X,Y\n"))
    assert len(esito.scartate) == 1
    assert esito.totale_letto == 3


def test_importa_da_bytes(conn):
    esito = importa_da_bytes(conn, INTESTATO.encode("utf-8-sig"))
    assert len(esito.inseriti) == 2


def test_resoconto_leggibile(conn):
    testo = render_esito(importa_righe(conn, parse_csv(INTESTATO + "abc,,X,Y\n")))
    assert "Inseriti: 2" in testo
    assert "Righe non valide: 1" in testo


def test_resoconto_file_illeggibile(conn):
    testo = render_esito(importa_righe(conn, parse_csv("")))
    assert "nessuna riga leggibile" in testo
