"""Import del Registro delle Attività da CSV: parsing e scrittura."""

import pytest

from anagrafe import repository
from anagrafe.csv_attivita import (
    importa_da_bytes,
    importa_righe,
    parse_csv,
    render_esito,
)

INTESTAZIONE = "Nome,Tipologia,Descrizione,Contatto,Proprietario"


def csv_testo(*righe, intestazione=True):
    corpo = list(righe)
    if intestazione:
        corpo.insert(0, INTESTAZIONE)
    return "\n".join(corpo) + "\n"


# ----------------------------------------------------------------------
# Parsing
# ----------------------------------------------------------------------

def test_una_riga_completa():
    parsing = parse_csv(
        csv_testo("Pizzeria Da Mario,Attività Privata,Pizza al taglio.,@pizzeria,111")
    )
    assert parsing.intestazione_trovata
    assert not parsing.scartate
    riga = parsing.righe[0]
    assert riga.nome_attivita == "Pizzeria Da Mario"
    assert riga.tipologia == "privata"  # l'etichetta diventa la chiave canonica
    assert riga.descrizione == "Pizza al taglio."
    assert riga.contatto_link == "@pizzeria"
    assert riga.proprietario == "111"


def test_il_contatto_e_facoltativo():
    parsing = parse_csv(csv_testo("Circolo,Associazione,Letture.,,111"))
    assert parsing.righe[0].contatto_link is None


@pytest.mark.parametrize(
    "scritta", ["Attività Privata", "attivita privata", "privata", "ATTIVITÀ PRIVATA"]
)
def test_la_tipologia_si_riconosce_in_ogni_forma(scritta):
    parsing = parse_csv(csv_testo(f"Bar,{scritta},Caffè.,,111"))
    assert parsing.righe[0].tipologia == "privata"


def test_una_tipologia_inventata_scarta_la_riga():
    parsing = parse_csv(csv_testo("Bar,Banca,Caffè.,,111"))
    assert not parsing.righe
    assert "Banca" in parsing.scartate[0].motivo


@pytest.mark.parametrize(
    "riga,pezzo",
    [
        (",Associazione,Descrizione.,,111", "nome"),
        ("Bar,Associazione,,,111", "descrizione"),
        ("Bar,Associazione,Caffè.,,", "proprietario"),
    ],
)
def test_le_colonne_obbligatorie_mancanti_scartano_la_riga(riga, pezzo):
    parsing = parse_csv(csv_testo(riga))
    assert not parsing.righe
    assert pezzo in parsing.scartate[0].motivo.lower()


def test_un_proprietario_illeggibile_scarta_la_riga():
    parsing = parse_csv(csv_testo("Bar,Associazione,Caffè.,,non-un-id"))
    assert not parsing.righe
    assert parsing.scartate


@pytest.mark.parametrize("proprietario", ["111", "#3", "@anna"])
def test_il_proprietario_si_indica_in_tre_modi(proprietario):
    parsing = parse_csv(csv_testo(f"Bar,Associazione,Caffè.,,{proprietario}"))
    assert parsing.righe[0].proprietario == proprietario


def test_due_righe_identiche_nel_file():
    parsing = parse_csv(
        csv_testo(
            "Bar Anna,Associazione,Prima.,,111",
            "bar anna,Associazione,Seconda.,,111",
        )
    )
    assert len(parsing.righe) == 1
    assert "duplicata" in parsing.scartate[0].motivo.lower()


def test_lo_stesso_nome_di_un_altro_proprietario_passa():
    parsing = parse_csv(
        csv_testo(
            "Bar Anna,Associazione,Di Anna.,,111",
            "Bar Anna,Associazione,Di Bruno.,,222",
        )
    )
    assert len(parsing.righe) == 2


def test_senza_intestazione_le_colonne_sono_posizionali():
    parsing = parse_csv(
        csv_testo("Bar,Associazione,Caffè.,@bar,111", intestazione=False)
    )
    assert not parsing.intestazione_trovata
    assert parsing.righe[0].nome_attivita == "Bar"
    assert parsing.righe[0].proprietario == "111"


def test_gli_alias_delle_intestazioni():
    testo = (
        "Denominazione;Categoria;Scopo;Recapito;Owner\n"
        "Bar;Associazione;Caffè.;@bar;111\n"
    )
    parsing = parse_csv(testo)
    assert parsing.intestazione_trovata
    assert parsing.righe[0].nome_attivita == "Bar"


def test_un_file_vuoto():
    parsing = parse_csv("")
    assert not parsing.righe and not parsing.scartate


def test_le_righe_vuote_si_ignorano():
    parsing = parse_csv(csv_testo("", "Bar,Associazione,Caffè.,,111", ""))
    assert len(parsing.righe) == 1


# ----------------------------------------------------------------------
# Scrittura sul registro
# ----------------------------------------------------------------------

def test_import_riuscito(conn, cittadino):
    parsing = parse_csv(csv_testo("Bar Anna,Associazione,Caffè.,@bar,12345"))
    esito = importa_righe(conn, parsing)

    assert len(esito.iscritte) == 1
    attivita_id, _ = esito.iscritte[0]
    riga = repository.get_attivita(conn, attivita_id)
    assert riga["nome_attivita"] == "Bar Anna"
    assert riga["owner_id"] == 12345
    assert riga["owner_username"] == "mariorossi"  # preso dal registro, non dal file
    assert riga["stato"] == repository.ATTIVITA_ATTIVA


def test_limport_non_pubblica_in_gazzetta(conn, cittadino):
    """Un file da cinquanta righe produrrebbe cinquanta post."""
    esito = importa_righe(
        conn, parse_csv(csv_testo("Bar,Associazione,Caffè.,,12345"))
    )
    attivita_id, _ = esito.iscritte[0]
    riga = repository.get_attivita(conn, attivita_id)
    assert riga["message_id_pubblico"] is None
    assert riga["chat_id_pubblico"] is None


def test_il_proprietario_deve_essere_cittadino(conn):
    esito = importa_righe(
        conn, parse_csv(csv_testo("Orfana,Associazione,Caffè.,,999999"))
    )
    assert not esito.iscritte
    assert len(esito.saltate) == 1
    assert "999999" in esito.saltate[0][0]


@pytest.mark.parametrize("riferimento", ["12345", "#1", "@mariorossi"])
def test_il_proprietario_si_risolve_nei_tre_modi(conn, cittadino, riferimento):
    esito = importa_righe(
        conn, parse_csv(csv_testo(f"Bar,Associazione,Caffè.,,{riferimento}"))
    )
    assert len(esito.iscritte) == 1
    attivita_id, _ = esito.iscritte[0]
    assert repository.get_attivita(conn, attivita_id)["owner_id"] == 12345


def test_un_nome_gia_attivo_viene_saltato(conn, cittadino, attivita):
    esito = importa_righe(
        conn, parse_csv(csv_testo("Pizzeria Da Mario,Associazione,Un'altra.,,12345"))
    )
    assert not esito.iscritte
    assert "nome" in esito.saltate[0][0].lower()


def test_un_nome_ritirato_torna_importabile(conn, cittadino, attivita):
    repository.chiudi_attivita(conn, attivita, repository.ATTIVITA_CHIUSA, 12345, None)
    esito = importa_righe(
        conn, parse_csv(csv_testo("Pizzeria Da Mario,Associazione,Di nuovo.,,12345"))
    )
    assert len(esito.iscritte) == 1


def test_le_righe_buone_passano_anche_se_altre_no(conn, cittadino):
    esito = importa_righe(
        conn,
        parse_csv(
            csv_testo(
                "Buona,Associazione,Va bene.,,12345",
                "Orfana,Associazione,Proprietario ignoto.,,999999",
                "Storta,Banca,Tipologia inventata.,,12345",
            )
        ),
    )
    assert len(esito.iscritte) == 1
    assert len(esito.saltate) == 1
    assert len(esito.scartate) == 1
    assert esito.totale_letto == 3


def test_importa_da_bytes(conn, cittadino):
    dati = csv_testo("Bar,Associazione,Caffè.,,12345").encode("utf-8")
    assert len(importa_da_bytes(conn, dati).iscritte) == 1


# ----------------------------------------------------------------------
# Resoconto
# ----------------------------------------------------------------------

def test_il_resoconto_conta_tutto(conn, cittadino):
    esito = importa_righe(
        conn,
        parse_csv(
            csv_testo(
                "Buona,Associazione,Va bene.,,12345",
                "Orfana,Associazione,Ignoto.,,999999",
                "Storta,Banca,Inventata.,,12345",
            )
        ),
    )
    testo = render_esito(esito)
    assert "Iscritte: 1" in testo
    assert "Saltate: 1" in testo
    assert "Righe non valide: 1" in testo
    assert "Gazzetta" in testo  # l'avviso sulla mancata pubblicazione


def test_il_resoconto_di_un_file_illeggibile():
    testo = render_esito(importa_righe(None, parse_csv("")))
    assert "nessuna riga leggibile" in testo


def test_senza_iscrizioni_non_si_parla_di_gazzetta():
    testo = render_esito(importa_righe(None, parse_csv("")))
    assert "Gazzetta" not in testo
