"""Controlli fail-fast e risoluzione dei riferimenti (#ID, @tag, ID Telegram)."""

import pytest

from anagrafe import controlli, repository
from anagrafe.validators import (
    RIF_CITIZEN_ID,
    RIF_NUMERO,
    RIF_TELEGRAM_ID,
    RIF_USERNAME,
    ErroreValidazione,
    Riferimento,
)


# ----------------------------------------------------------------------
# Richiesta di cittadinanza
# ----------------------------------------------------------------------

def test_richiesta_possibile(conn):
    controlli.precondizione_richiedi(conn, 555)


def test_richiesta_di_chi_e_gia_cittadino(conn, cittadino):
    with pytest.raises(ErroreValidazione, match=f"#{cittadino}"):
        controlli.precondizione_richiedi(conn, 12345)


def test_richiesta_con_unaltra_in_attesa(conn):
    request_id = repository.create_request(conn, 555, None, "Carlo", "Neri")
    with pytest.raises(ErroreValidazione, match=f"#{request_id}"):
        controlli.precondizione_richiedi(conn, 555)


# ----------------------------------------------------------------------
# Riferimenti a un cittadino
# ----------------------------------------------------------------------

@pytest.mark.parametrize(
    "rif",
    [
        Riferimento(RIF_CITIZEN_ID, 1),
        Riferimento(RIF_TELEGRAM_ID, 12345),
        Riferimento(RIF_USERNAME, "mariorossi"),
        Riferimento(RIF_USERNAME, "MarioRossi"),  # i tag Telegram ignorano le maiuscole
    ],
)
def test_risolvi_cittadino(conn, cittadino, rif):
    assert controlli.risolvi_cittadino(conn, rif)["citizen_id"] == cittadino


@pytest.mark.parametrize(
    "rif",
    [
        Riferimento(RIF_CITIZEN_ID, 99),
        Riferimento(RIF_TELEGRAM_ID, 99),
        Riferimento(RIF_USERNAME, "nessuno"),
    ],
)
def test_risolvi_cittadino_inesistente(conn, cittadino, rif):
    with pytest.raises(ErroreValidazione, match=str(rif)):
        controlli.risolvi_cittadino(conn, rif)


def test_numero_nudo_vale_come_id_cittadino_o_telegram(conn, cittadino):
    """Chi rimuove non deve ricordarsi quale dei due ID sta scrivendo."""
    per_id = controlli.risolvi_cittadino(conn, Riferimento(RIF_NUMERO, cittadino))
    per_telegram = controlli.risolvi_cittadino(conn, Riferimento(RIF_NUMERO, 12345))
    assert per_id["citizen_id"] == per_telegram["citizen_id"] == cittadino


def test_numero_nudo_inesistente(conn, cittadino):
    with pytest.raises(ErroreValidazione, match="ID cittadino o ID Telegram 999"):
        controlli.risolvi_cittadino(conn, Riferimento(RIF_NUMERO, 999))


def test_numero_nudo_ambiguo(conn):
    """Il numero è l'ID cittadino di uno e l'ID Telegram di un altro."""
    primo = repository.insert_citizen(conn, 50, None, "Mario", "Rossi")
    secondo = repository.insert_citizen(conn, primo, None, "Luigi", "Bianchi")
    with pytest.raises(ErroreValidazione, match=f"#{primo}.*#{secondo}"):
        controlli.risolvi_cittadino(conn, Riferimento(RIF_NUMERO, primo))


def test_tag_ambiguo_chiede_lid(conn):
    """Dati vecchi potrebbero avere lo stesso tag su due cittadini."""
    primo = repository.insert_citizen(conn, 1, "doppio", "Mario", "Rossi")
    secondo = repository.insert_citizen(conn, 2, "doppio", "Luigi", "Bianchi")
    with pytest.raises(ErroreValidazione, match=f"#{primo}, #{secondo}"):
        controlli.risolvi_cittadino(conn, Riferimento(RIF_USERNAME, "doppio"))


def test_risolvi_telegram_id(conn, cittadino):
    assert controlli.risolvi_telegram_id(conn, Riferimento(RIF_USERNAME, "mariorossi")) == 12345
    # Un ID Telegram non ha bisogno di essere un cittadino.
    assert controlli.risolvi_telegram_id(conn, Riferimento(RIF_TELEGRAM_ID, 777)) == 777


def test_nuovo_cittadino(conn, cittadino):
    controlli.verifica_nuovo_cittadino(conn, 999)
    with pytest.raises(ErroreValidazione, match=f"#{cittadino}"):
        controlli.verifica_nuovo_cittadino(conn, 12345)


# ----------------------------------------------------------------------
# Amministratori
# ----------------------------------------------------------------------

def test_nuovo_admin(roles, root_id):
    controlli.verifica_nuovo_admin(roles, 222)
    roles.aggiungi(222)
    with pytest.raises(ErroreValidazione, match="già un amministratore"):
        controlli.verifica_nuovo_admin(roles, 222)
    with pytest.raises(ErroreValidazione, match="root"):
        controlli.verifica_nuovo_admin(roles, root_id)


def test_admin_rimovibile(roles, root_id):
    with pytest.raises(ErroreValidazione, match="non risulta"):
        controlli.verifica_admin_rimovibile(roles, 222)
    roles.aggiungi(222)
    controlli.verifica_admin_rimovibile(roles, 222)
    with pytest.raises(ErroreValidazione, match="root"):
        controlli.verifica_admin_rimovibile(roles, root_id)


# ----------------------------------------------------------------------
# Registro delle attività
# ----------------------------------------------------------------------

def test_solo_un_cittadino_puo_iscrivere_unattivita(conn, cittadino):
    riga = controlli.precondizione_attivita(conn, 12345)
    assert riga["citizen_id"] == cittadino


def test_un_estraneo_viene_rimandato_a_richiedi(conn):
    """È il requisito di cittadinanza del D.M. n.3 del 13/10/2026."""
    with pytest.raises(ErroreValidazione, match="/richiedi_cittadinanza"):
        controlli.precondizione_attivita(conn, 99999)


def test_nome_libero(conn, cittadino):
    assert controlli.verifica_nome_attivita_libero(conn, 12345, "Bar Nuovo") == "Bar Nuovo"


def test_nome_gia_usato_dallo_stesso_proprietario(conn, cittadino, attivita):
    with pytest.raises(ErroreValidazione, match=f"#{attivita}"):
        controlli.verifica_nome_attivita_libero(conn, 12345, "pizzeria da mario")


def test_lo_stesso_nome_di_un_altro_proprietario_e_ammesso(conn, cittadino, attivita):
    assert controlli.verifica_nome_attivita_libero(conn, 777, "Pizzeria Da Mario")


def test_il_nome_di_unattivita_rimossa_torna_libero(conn, cittadino, attivita):
    repository.chiudi_attivita(conn, attivita, repository.ATTIVITA_RIMOSSA, 100, "capo")
    assert controlli.verifica_nome_attivita_libero(conn, 12345, "Pizzeria Da Mario")


def test_risolvi_attivita(conn, cittadino, attivita):
    assert controlli.risolvi_attivita(conn, attivita)["attivita_id"] == attivita


def test_risolvi_attivita_inesistente(conn):
    with pytest.raises(ErroreValidazione, match="#999"):
        controlli.risolvi_attivita(conn, 999)


def test_attivita_moderabile(conn, cittadino, attivita):
    assert controlli.verifica_attivita_moderabile(conn, attivita)["stato"] == "ATTIVA"


def test_attivita_gia_moderata(conn, cittadino, attivita):
    repository.chiudi_attivita(conn, attivita, repository.ATTIVITA_RIMOSSA, 100, "capo")
    with pytest.raises(ErroreValidazione, match="rimossa"):
        controlli.verifica_attivita_moderabile(conn, attivita)


# ----------------------------------------------------------------------
# Rimozione di un'attività: il permesso dipende dalla proprietà
# ----------------------------------------------------------------------

def test_il_proprietario_puo_rimuovere_la_sua(conn, cittadino, attivita):
    riga = controlli.verifica_attivita_rimovibile(conn, attivita, 12345, False)
    assert riga["attivita_id"] == attivita


def test_un_estraneo_non_puo_rimuovere_laltrui(conn, cittadino, attivita):
    with pytest.raises(ErroreValidazione):
        controlli.verifica_attivita_rimovibile(conn, attivita, 99999, False)


def test_il_rifiuto_non_rivela_nulla_dellattivita(conn, cittadino, attivita):
    """Chi indovina un ID non deve scoprire né che esiste né di chi è."""
    with pytest.raises(ErroreValidazione) as esistente:
        controlli.verifica_attivita_rimovibile(conn, attivita, 99999, False)
    with pytest.raises(ErroreValidazione) as inventata:
        controlli.verifica_attivita_rimovibile(conn, 999, 99999, False)

    assert "Pizzeria" not in str(esistente.value)
    # Lo stesso messaggio nei due casi, a meno dell'ID.
    assert str(esistente.value).replace(str(attivita), "X") == str(
        inventata.value
    ).replace("999", "X")


def test_un_admin_puo_rimuovere_qualunque_attivita(conn, cittadino, attivita):
    riga = controlli.verifica_attivita_rimovibile(conn, attivita, 99999, True)
    assert riga["attivita_id"] == attivita


def test_non_si_rimuove_unattivita_gia_chiusa(conn, cittadino, attivita):
    repository.chiudi_attivita(conn, attivita, repository.ATTIVITA_CHIUSA, 12345, None)
    with pytest.raises(ErroreValidazione, match="chiusa"):
        controlli.verifica_attivita_rimovibile(conn, attivita, 12345, False)


def test_unattivita_inesistente_non_si_rimuove(conn, cittadino):
    with pytest.raises(ErroreValidazione, match="#999"):
        controlli.verifica_attivita_rimovibile(conn, 999, 12345, True)


def test_il_nome_di_unattivita_ritirata_torna_libero(conn, cittadino, attivita):
    """È il presupposto del «si rimuove e si reimmette»."""
    repository.chiudi_attivita(conn, attivita, repository.ATTIVITA_CHIUSA, 12345, None)
    assert controlli.verifica_nome_attivita_libero(conn, 12345, "Pizzeria Da Mario")
