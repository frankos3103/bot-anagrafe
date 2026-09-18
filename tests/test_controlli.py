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
