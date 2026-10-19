"""Query sul Registro Pubblico delle Attività (D.M. n.3 del 13/10/2026)."""

import sqlite3

import pytest

from anagrafe import repository


def _crea(conn, nome, owner_id=12345, tipologia="privata"):
    return repository.create_attivita(
        conn,
        owner_id=owner_id,
        owner_username=None,
        nome_attivita=nome,
        tipologia=tipologia,
        descrizione="Una descrizione.",
    )


# ----------------------------------------------------------------------
# Iscrizione e rilettura
# ----------------------------------------------------------------------

def test_iscrivi_e_rileggi(conn, attivita):
    riga = repository.get_attivita(conn, attivita)
    assert riga["nome_attivita"] == "Pizzeria Da Mario"
    assert riga["tipologia"] == "privata"
    assert riga["contatto_link"] == "@pizzeriadamario"
    assert riga["owner_id"] == 12345
    assert riga["created_at"] == repository.oggi()


def test_nasce_attiva(conn, attivita):
    """Il decreto non prevede approvazione preventiva: è attiva subito."""
    assert repository.get_attivita(conn, attivita)["stato"] == repository.ATTIVITA_ATTIVA


def test_lusername_del_proprietario_viene_normalizzato(conn, cittadino):
    attivita_id = repository.create_attivita(
        conn, 12345, "@mariorossi", "Bar", "privata", "Caffè."
    )
    assert repository.get_attivita(conn, attivita_id)["owner_username"] == "mariorossi"


def test_attivita_inesistente(conn):
    assert repository.get_attivita(conn, 999) is None


# ----------------------------------------------------------------------
# Elenco pubblico
# ----------------------------------------------------------------------

def test_lelenco_mostra_solo_le_attive(conn, cittadino, attivita):
    altra = _crea(conn, "Circolo Zeta")
    repository.chiudi_attivita(conn, altra, repository.ATTIVITA_RIMOSSA, 100, "admin")

    nomi = [r["nome_attivita"] for r in repository.list_attivita_attive(conn)]
    assert nomi == ["Pizzeria Da Mario"]
    assert repository.count_attivita_attive(conn) == 1


def test_lelenco_ignora_maiuscole_e_accenti(conn, cittadino):
    """Come /elenco_cittadini: il COLLATE NOCASE di SQLite vale solo per l'ASCII."""
    for nome in ("Zeta", "Élite", "banca"):
        _crea(conn, nome)

    nomi = [r["nome_attivita"] for r in repository.list_attivita_attive(conn)]
    assert nomi == ["banca", "Élite", "Zeta"]


def test_elenco_vuoto(conn):
    assert repository.list_attivita_attive(conn) == []
    assert repository.count_attivita_attive(conn) == 0


def test_elenco_per_proprietario(conn, cittadino, attivita):
    _crea(conn, "Altrui", owner_id=777)

    mie = repository.list_attivita_per_owner(conn, 12345)
    assert [r["attivita_id"] for r in mie] == [attivita]


def test_elenco_per_proprietario_comprese_le_chiuse(conn, cittadino, attivita):
    repository.chiudi_attivita(conn, attivita, repository.ATTIVITA_RIMOSSA, 100, "admin")

    assert repository.list_attivita_per_owner(conn, 12345) == []
    assert len(repository.list_attivita_per_owner(conn, 12345, solo_attive=False)) == 1


# ----------------------------------------------------------------------
# Un nome per proprietario
# ----------------------------------------------------------------------

def test_nome_trovato_ignorando_maiuscole_e_accenti(conn, cittadino, attivita):
    trovata = repository.attivita_per_nome(conn, 12345, "PIZZERIA da mario")
    assert trovata["attivita_id"] == attivita


def test_lo_stesso_nome_di_un_altro_proprietario_e_libero(conn, cittadino, attivita):
    assert repository.attivita_per_nome(conn, 777, "Pizzeria Da Mario") is None


def test_il_nome_torna_libero_dopo_la_rimozione(conn, cittadino, attivita):
    repository.chiudi_attivita(conn, attivita, repository.ATTIVITA_RIMOSSA, 100, "admin")

    assert repository.attivita_per_nome(conn, 12345, "Pizzeria Da Mario") is None
    nuova = _crea(conn, "Pizzeria Da Mario")
    assert repository.attivita_per_nome(conn, 12345, "pizzeria da mario")["attivita_id"] == nuova


def test_due_attive_omonime_sono_impedite_dallindice(conn, cittadino, attivita):
    """L'indice unico parziale è l'ultima barriera sotto ai controlli."""
    with pytest.raises(sqlite3.IntegrityError):
        _crea(conn, "Pizzeria Da Mario")


# ----------------------------------------------------------------------
# Moderazione: l'UPDATE condizionato fa da lock
# ----------------------------------------------------------------------

def test_chiusura_riuscita(conn, cittadino, attivita):
    assert repository.chiudi_attivita(
        conn, attivita, repository.ATTIVITA_RIMOSSA, 100, "@capo"
    )
    riga = repository.get_attivita(conn, attivita)
    assert riga["stato"] == repository.ATTIVITA_RIMOSSA
    assert riga["admin_id"] == 100
    assert riga["admin_username"] == "capo"  # la @ viene tolta
    assert riga["data_moderazione"] == repository.oggi()


def test_la_seconda_moderazione_non_passa(conn, cittadino, attivita):
    """Due amministratori che premono insieme non producono due moderazioni."""
    assert repository.chiudi_attivita(
        conn, attivita, repository.ATTIVITA_RIMOSSA, 100, "capo"
    )
    assert not repository.chiudi_attivita(
        conn, attivita, repository.ATTIVITA_RIMOSSA, 200, "altro"
    )

    riga = repository.get_attivita(conn, attivita)
    assert riga["stato"] == repository.ATTIVITA_RIMOSSA
    assert riga["admin_id"] == 100


def test_chiusura_di_unattivita_inesistente(conn):
    assert not repository.chiudi_attivita(
        conn, 999, repository.ATTIVITA_RIMOSSA, 100, "capo"
    )


# ----------------------------------------------------------------------
# Riferimenti al post in Gazzetta e alle notifiche
# ----------------------------------------------------------------------

def test_riferimento_al_post(conn, cittadino, attivita):
    repository.set_attivita_post(conn, attivita, "@gazzetta_ciompista", 42)
    riga = repository.get_attivita(conn, attivita)
    assert riga["chat_id_pubblico"] == "@gazzetta_ciompista"
    assert riga["message_id_pubblico"] == 42


def test_chat_id_numerico_salvato_come_testo(conn, cittadino, attivita):
    """Il canale può essere un @nomecanale: la colonna è TEXT per entrambi."""
    repository.set_attivita_post(conn, attivita, -1001234567890, 42)
    assert repository.get_attivita(conn, attivita)["chat_id_pubblico"] == "-1001234567890"


def test_riferimento_azzerabile(conn, cittadino, attivita):
    repository.set_attivita_post(conn, attivita, "@gazzetta", 42)
    repository.set_attivita_post(conn, attivita, None, None)
    riga = repository.get_attivita(conn, attivita)
    assert riga["chat_id_pubblico"] is None
    assert riga["message_id_pubblico"] is None


def test_notifiche_andata_e_ritorno(conn, cittadino, attivita):
    repository.set_attivita_notifiche(conn, attivita, [[10, 1], [20, 2]])
    riga = repository.get_attivita(conn, attivita)
    assert repository.load_notifiche(riga["notifiche"]) == [(10, 1), (20, 2)]


@pytest.mark.parametrize("grezzo", [None, "", "{rotto", "[[1]]", '["a","b"]'])
def test_notifiche_illeggibili(grezzo):
    assert repository.load_notifiche(grezzo) == []


def test_il_nome_storico_resta_disponibile():
    """richieste.py e i test esistenti usano ancora load_request_notifications."""
    assert repository.load_request_notifications is repository.load_notifiche


# ----------------------------------------------------------------------
# Ritiro volontario: stato distinto dall'atto d'ufficio
# ----------------------------------------------------------------------

def test_il_ritiro_volontario_ha_uno_stato_suo(conn, cittadino, attivita):
    assert repository.chiudi_attivita(
        conn, attivita, repository.ATTIVITA_CHIUSA, 12345, "mariorossi"
    )
    riga = repository.get_attivita(conn, attivita)
    assert riga["stato"] == repository.ATTIVITA_CHIUSA
    # Le colonne admin_* registrano chi ha chiuso: qui il proprietario.
    assert riga["admin_id"] == 12345


def test_unattivita_ritirata_esce_dallelenco(conn, cittadino, attivita):
    repository.chiudi_attivita(conn, attivita, repository.ATTIVITA_CHIUSA, 12345, None)
    assert repository.list_attivita_attive(conn) == []
    assert repository.count_attivita_attive(conn) == 0


def test_una_moderazione_dopo_un_ritiro_perde(conn, cittadino, attivita):
    """Il compare-and-swap vale per tutti gli stati di arrivo."""
    assert repository.chiudi_attivita(
        conn, attivita, repository.ATTIVITA_CHIUSA, 12345, None
    )
    assert not repository.chiudi_attivita(
        conn, attivita, repository.ATTIVITA_RIMOSSA, 100, "capo"
    )
    assert repository.get_attivita(conn, attivita)["stato"] == repository.ATTIVITA_CHIUSA


def test_rimuovi_e_reimmetti(conn, cittadino, attivita):
    """La correzione di un'attività si fa così: l'indice unico è parziale."""
    repository.chiudi_attivita(conn, attivita, repository.ATTIVITA_CHIUSA, 12345, None)
    nuova = _crea(conn, "Pizzeria Da Mario")
    assert nuova != attivita
    nomi = [r["nome_attivita"] for r in repository.list_attivita_attive(conn)]
    assert nomi == ["Pizzeria Da Mario"]


def test_ogni_stato_ha_unetichetta_leggibile():
    for stato in (
        repository.ATTIVITA_ATTIVA,
        repository.ATTIVITA_CHIUSA,
        repository.ATTIVITA_RIMOSSA,
    ):
        assert repository.ETICHETTE_STATO_ATTIVITA[stato]
