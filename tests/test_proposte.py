"""Le proposte di attività: esistono solo finché sono in attesa.

Approvarle le sposta nel registro, rifiutarle le cancella. In nessuno dei due
casi resta una proposta nel database, e un rifiuto non lascia alcuna traccia.
"""

import sqlite3

import pytest

from anagrafe import controlli, repository
from anagrafe.validators import ErroreValidazione


def _proponi(conn, nome, owner_id=12345, tipologia="privata"):
    return repository.crea_proposta(
        conn,
        owner_id=owner_id,
        owner_username=None,
        nome_attivita=nome,
        tipologia=tipologia,
        descrizione="Una descrizione.",
    )


# ----------------------------------------------------------------------
# Proporre
# ----------------------------------------------------------------------

def test_una_proposta_non_entra_nel_registro(conn, cittadino, proposta):
    """È il punto del modello: approvazione preventiva."""
    assert repository.list_attivita_attive(conn) == []
    assert repository.count_attivita_attive(conn) == 0
    assert repository.count_proposte(conn) == 1


def test_proponi_e_rileggi(conn, cittadino, proposta):
    riga = repository.get_proposta(conn, proposta)
    assert riga["nome_attivita"] == "Bar Nuovo"
    assert riga["tipologia"] == "privata"
    assert riga["contatto_link"] == "@barnuovo"
    assert riga["owner_id"] == 12345
    assert riga["created_at"] == repository.oggi()


def test_lusername_del_proponente_viene_normalizzato(conn, cittadino):
    proposta_id = repository.crea_proposta(
        conn, 12345, "@mariorossi", "Bar", "privata", "Caffè."
    )
    assert repository.get_proposta(conn, proposta_id)["owner_username"] == "mariorossi"


def test_una_proposta_inesistente(conn):
    assert repository.get_proposta(conn, 999) is None


def test_le_proposte_si_esaminano_in_ordine_di_arrivo(conn, cittadino):
    primo = _proponi(conn, "Prima")
    secondo = _proponi(conn, "Seconda")
    assert [p["proposta_id"] for p in repository.list_proposte(conn)] == [
        primo,
        secondo,
    ]


def test_proposte_per_proprietario(conn, cittadino, proposta):
    _proponi(conn, "Altrui", owner_id=777)
    mie = repository.list_proposte_per_owner(conn, 12345)
    assert [p["proposta_id"] for p in mie] == [proposta]


def test_proposta_per_nome_ignora_maiuscole_e_accenti(conn, cittadino, proposta):
    assert repository.proposta_per_nome(conn, 12345, "BAR nuovo")["proposta_id"] == proposta
    assert repository.proposta_per_nome(conn, 777, "Bar Nuovo") is None


def test_due_proposte_omonime_sono_impedite_dallindice(conn, cittadino, proposta):
    with pytest.raises(sqlite3.IntegrityError):
        _proponi(conn, "bar nuovo")


# ----------------------------------------------------------------------
# Approvare
# ----------------------------------------------------------------------

def test_lapprovazione_sposta_nel_registro(conn, cittadino, proposta):
    attivita_id, riga = repository.approva_proposta(conn, proposta, 100, "@capo")

    assert repository.get_proposta(conn, proposta) is None, "la proposta va via"
    attivita = repository.get_attivita(conn, attivita_id)
    assert attivita["nome_attivita"] == "Bar Nuovo"
    assert attivita["tipologia"] == "privata"
    assert attivita["contatto_link"] == "@barnuovo"
    assert attivita["owner_id"] == 12345
    assert attivita["stato"] == repository.ATTIVITA_ATTIVA
    assert riga["nome_attivita"] == "Bar Nuovo"


def test_lapprovazione_registra_chi_ha_approvato(conn, cittadino, proposta):
    attivita_id, _ = repository.approva_proposta(conn, proposta, 100, "@capo")
    riga = repository.get_attivita(conn, attivita_id)
    assert riga["admin_id"] == 100
    assert riga["admin_username"] == "capo"  # la @ viene tolta
    assert riga["data_moderazione"] == repository.oggi()


def test_unattivita_approvata_compare_nellelenco(conn, cittadino, proposta):
    repository.approva_proposta(conn, proposta, 100, "capo")
    assert [a["nome_attivita"] for a in repository.list_attivita_attive(conn)] == [
        "Bar Nuovo"
    ]


def test_unattivita_approvata_nasce_senza_post(conn, cittadino, proposta):
    """Il post lo scrive il gestore dopo l'approvazione, non il repository."""
    attivita_id, _ = repository.approva_proposta(conn, proposta, 100, "capo")
    riga = repository.get_attivita(conn, attivita_id)
    assert riga["message_id_pubblico"] is None
    assert riga["chat_id_pubblico"] is None


def test_approvare_una_proposta_inesistente(conn):
    assert repository.approva_proposta(conn, 999, 100, "capo") is None


def test_la_seconda_approvazione_non_passa(conn, cittadino, proposta):
    """È la DELETE a fare da lock: chi arriva secondo trova il vuoto."""
    assert repository.approva_proposta(conn, proposta, 100, "capo") is not None
    assert repository.approva_proposta(conn, proposta, 200, "altro") is None
    assert repository.count_attivita_attive(conn) == 1


def test_se_liscrizione_fallisce_la_proposta_resta(conn, cittadino):
    """Le due scritture stanno in una transazione sola.

    Se il nome risulta occupato al momento dell'approvazione, la cancellazione
    della proposta viene annullata insieme all'iscrizione.
    """
    repository.create_attivita(conn, 12345, None, "Bar Nuovo", "privata", "Già mio.")
    proposta_id = _proponi(conn, "Bar Nuovo", owner_id=12345)

    with pytest.raises(sqlite3.IntegrityError):
        repository.approva_proposta(conn, proposta_id, 100, "capo")

    conn.rollback()
    assert repository.get_proposta(conn, proposta_id) is not None
    assert repository.count_attivita_attive(conn) == 1


# ----------------------------------------------------------------------
# Rifiutare
# ----------------------------------------------------------------------

def test_il_rifiuto_cancella_e_non_lascia_traccia(conn, cittadino, proposta):
    riga = repository.rifiuta_proposta(conn, proposta)

    assert riga["nome_attivita"] == "Bar Nuovo", "la riga torna, per avvisare"
    assert repository.get_proposta(conn, proposta) is None
    assert repository.count_proposte(conn) == 0
    assert repository.count_attivita_attive(conn) == 0, "nel registro non entra nulla"


def test_rifiutare_una_proposta_inesistente(conn):
    assert repository.rifiuta_proposta(conn, 999) is None


def test_il_secondo_rifiuto_non_passa(conn, cittadino, proposta):
    assert repository.rifiuta_proposta(conn, proposta) is not None
    assert repository.rifiuta_proposta(conn, proposta) is None


def test_rifiutare_dopo_unapprovazione_non_passa(conn, cittadino, proposta):
    repository.approva_proposta(conn, proposta, 100, "capo")
    assert repository.rifiuta_proposta(conn, proposta) is None
    assert repository.count_attivita_attive(conn) == 1, "l'attività resta iscritta"


def test_dopo_un_rifiuto_il_nome_torna_proponibile(conn, cittadino, proposta):
    repository.rifiuta_proposta(conn, proposta)
    assert controlli.verifica_nome_attivita_libero(conn, 12345, "Bar Nuovo")
    assert _proponi(conn, "Bar Nuovo")


# ----------------------------------------------------------------------
# Notifiche
# ----------------------------------------------------------------------

def test_notifiche_andata_e_ritorno(conn, cittadino, proposta):
    repository.set_proposta_notifiche(conn, proposta, [[10, 1], [20, 2]])
    riga = repository.get_proposta(conn, proposta)
    assert repository.load_notifiche(riga["notifiche"]) == [(10, 1), (20, 2)]


# ----------------------------------------------------------------------
# Il nome deve essere libero su due fronti
# ----------------------------------------------------------------------

def test_non_si_propone_un_nome_gia_proposto(conn, cittadino, proposta):
    with pytest.raises(ErroreValidazione, match="in attesa"):
        controlli.verifica_nome_attivita_libero(conn, 12345, "bar nuovo")


def test_non_si_propone_un_nome_gia_iscritto(conn, cittadino, attivita):
    with pytest.raises(ErroreValidazione, match=f"#{attivita}"):
        controlli.verifica_nome_attivita_libero(conn, 12345, "Pizzeria Da Mario")


def test_lo_stesso_nome_proposto_da_un_altro_e_ammesso(conn, cittadino, proposta):
    assert controlli.verifica_nome_attivita_libero(conn, 777, "Bar Nuovo")
