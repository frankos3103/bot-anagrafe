"""I file di export: Markdown da leggere, CSV da reimportare."""

import pytest

from anagrafe.csv_import import decodifica, parse_csv
from anagrafe.esportazione import (
    COLONNE_ATTIVITA,
    COLONNE_CITTADINI,
    FORMATO_CSV,
    FORMATO_MD,
    FORMATO_PREDEFINITO,
    esporta_attivita,
    esporta_cittadini,
    tabella_markdown,
    tabella_markdown_attivita,
)


def cittadino(citizen_id=1, telegram_id=111, username="mariorossi", nome="Mario",
              cognome="Rossi"):
    return {
        "citizen_id": citizen_id,
        "telegram_id": telegram_id,
        "username": username,
        "nome": nome,
        "cognome": cognome,
    }


def attivita(attivita_id=1, nome="Pizzeria Da Mario", tipologia="privata",
             descrizione="Pizza al taglio.", contatto="@pizzeria", owner_id=111):
    return {
        "attivita_id": attivita_id,
        "nome_attivita": nome,
        "tipologia": tipologia,
        "descrizione": descrizione,
        "contatto_link": contatto,
        "owner_id": owner_id,
    }


def _righe_csv(documento):
    return decodifica(documento.contenuto).splitlines()


# ----------------------------------------------------------------------
# Markdown
# ----------------------------------------------------------------------

def test_tabella_markdown():
    testo = tabella_markdown(
        [cittadino(), cittadino(2, 222, None, "Luigi", "Bianchi")], 2
    )
    assert "# Registro Cittadini" in testo
    assert "Totale cittadini: 2" in testo
    assert "| 1 | 111 | @mariorossi | Mario | ROSSI |" in testo
    assert "| 2 | 222 |  | Luigi | BIANCHI |" in testo
    assert testo.endswith("\n")


def test_tabella_markdown_sfugge_le_pipe():
    assert r"Mario\|Luigi" in tabella_markdown([cittadino(nome="Mario|Luigi")], 1)


@pytest.mark.parametrize("cognome", ["Zaccaria", "ZACCARIA", "zaccaria"])
def test_nel_markdown_il_cognome_e_maiuscolo(cognome):
    """Come in tutti gli elenchi del progetto."""
    testo = tabella_markdown([cittadino(nome="Giovanni", cognome=cognome)], 1)
    assert "| Giovanni | ZACCARIA |" in testo


def test_tabella_markdown_attivita():
    testo = tabella_markdown_attivita([attivita()], 1)
    assert "# Registro Pubblico delle Attività" in testo
    assert "Totale attività: 1" in testo
    assert "| 1 | Pizzeria Da Mario | Attività Privata |" in testo
    assert "| @pizzeria | 111 |" in testo


def test_la_tipologia_si_esporta_col_nome_pubblico():
    """Nel file va «Associazione», non lo slug «associazione»."""
    testo = tabella_markdown_attivita([attivita(tipologia="associazione")], 1)
    assert "Associazione" in testo


def test_unattivita_senza_contatto_lascia_la_cella_vuota():
    testo = tabella_markdown_attivita([attivita(contatto=None)], 1)
    assert "|  | 111 |" in testo


def test_la_descrizione_con_una_pipe_non_rompe_la_tabella():
    testo = tabella_markdown_attivita([attivita(descrizione="a|b")], 1)
    assert r"a\|b" in testo


# ----------------------------------------------------------------------
# CSV
# ----------------------------------------------------------------------

def test_il_csv_dei_cittadini_ha_le_intestazioni_attese():
    righe = _righe_csv(esporta_cittadini([cittadino()], FORMATO_CSV))
    assert righe[0] == ",".join(COLONNE_CITTADINI)
    assert righe[1] == "1,111,@mariorossi,Mario,Rossi"


def test_il_csv_delle_attivita_ha_le_intestazioni_attese():
    righe = _righe_csv(esporta_attivita([attivita()], FORMATO_CSV))
    assert righe[0] == ",".join(COLONNE_ATTIVITA)


def test_nel_csv_il_cognome_resta_come_nel_registro():
    """Il CSV serve a rientrare dall'import: non deve alterare i dati."""
    righe = _righe_csv(esporta_cittadini([cittadino(cognome="Rossi")], FORMATO_CSV))
    assert righe[1].endswith(",Rossi")


def test_il_csv_quota_i_campi_con_la_virgola():
    documento = esporta_attivita([attivita(descrizione="Caffè, cornetti")], FORMATO_CSV)
    assert '"Caffè, cornetti"' in decodifica(documento.contenuto)


def test_il_csv_ha_il_bom_per_excel():
    """Senza, Excel mostra i nomi accentati illeggibili."""
    documento = esporta_cittadini([cittadino(cognome="Erésia")], FORMATO_CSV)
    assert documento.contenuto.startswith(b"\xef\xbb\xbf")
    assert "Erésia" in decodifica(documento.contenuto)


# ----------------------------------------------------------------------
# Nomi dei file e formato predefinito
# ----------------------------------------------------------------------

@pytest.mark.parametrize(
    "esporta,formato,atteso",
    [
        (esporta_cittadini, FORMATO_MD, "registro_cittadini.md"),
        (esporta_cittadini, FORMATO_CSV, "registro_cittadini.csv"),
        (esporta_attivita, FORMATO_MD, "registro_attivita.md"),
        (esporta_attivita, FORMATO_CSV, "registro_attivita.csv"),
    ],
)
def test_il_nome_del_file_dice_registro_e_formato(esporta, formato, atteso):
    righe = [cittadino()] if esporta is esporta_cittadini else [attivita()]
    assert esporta(righe, formato).nome_file == atteso


def test_un_formato_sconosciuto_ricade_sul_markdown():
    """Meglio un file leggibile che un errore: il formato arriva validato."""
    assert esporta_cittadini([cittadino()], "inventato").nome_file.endswith(".md")


def test_il_formato_predefinito_e_quello_di_prima():
    assert FORMATO_PREDEFINITO == FORMATO_MD


def test_un_registro_vuoto_produce_solo_le_intestazioni():
    righe = _righe_csv(esporta_cittadini([], FORMATO_CSV))
    assert righe == [",".join(COLONNE_CITTADINI)]


# ----------------------------------------------------------------------
# L'invariante: il CSV esportato rientra dall'import
# ----------------------------------------------------------------------

def test_i_cittadini_esportati_in_csv_rientrano_dallimport():
    """È ciò che lega l'export all'import: nessun ritocco a mano.

    Se le intestazioni di esportazione e gli alias di csv_import si
    disallineassero, il file prodotto dal bot non sarebbe rileggibile dal bot.
    """
    originali = [
        cittadino(1, 571374004, "aeZez2Au", "Giovanni", "Zaccaria"),
        cittadino(2, 222, None, "Massimiliano", "Erésia"),
    ]
    documento = esporta_cittadini(originali, FORMATO_CSV)

    parsing = parse_csv(decodifica(documento.contenuto))

    assert parsing.intestazione_trovata
    assert parsing.scartate == []
    assert [r.telegram_id for r in parsing.righe] == [571374004, 222]
    assert [r.username for r in parsing.righe] == ["aeZez2Au", None]
    assert [r.cognome for r in parsing.righe] == ["Zaccaria", "Erésia"]


def test_le_attivita_esportate_in_csv_rientrano_dal_parser():
    from anagrafe.csv_attivita import parse_csv as parse_attivita

    originali = [
        attivita(1, "Pizzeria Da Mario", "privata", "Pizza, al taglio.", "@pizzeria", 111),
        attivita(2, "Circolo dei Ciompi", "associazione", "Letture.", None, 222),
    ]
    documento = esporta_attivita(originali, FORMATO_CSV)

    parsing = parse_attivita(decodifica(documento.contenuto))

    assert parsing.intestazione_trovata
    assert parsing.scartate == []
    assert [r.nome_attivita for r in parsing.righe] == [
        "Pizzeria Da Mario",
        "Circolo dei Ciompi",
    ]
    # L'etichetta pubblica torna a essere la chiave canonica.
    assert [r.tipologia for r in parsing.righe] == ["privata", "associazione"]
    assert [r.contatto_link for r in parsing.righe] == ["@pizzeria", None]
    assert [r.proprietario for r in parsing.righe] == ["111", "222"]
