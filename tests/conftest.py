"""Fixture condivise: un registro vuoto e un elenco amministratori su disco.

Nessun test tocca Telegram: qui si verifica solo la logica del bot.
"""

from __future__ import annotations

import sqlite3

import pytest

from anagrafe.db import get_connection, init_db
from anagrafe.roles import RoleRegistry

ROOT_ID = 100


@pytest.fixture
def root_id() -> int:
    return ROOT_ID


@pytest.fixture
def db_path(tmp_path):
    percorso = tmp_path / "registro.db"
    init_db(percorso)
    return percorso


@pytest.fixture
def conn(db_path) -> sqlite3.Connection:
    connessione = get_connection(db_path)
    try:
        yield connessione
    finally:
        connessione.close()


@pytest.fixture
def admins_path(tmp_path):
    return tmp_path / "admins.txt"


@pytest.fixture
def roles(admins_path) -> RoleRegistry:
    return RoleRegistry(root_admin_id=ROOT_ID, admins_path=admins_path)


@pytest.fixture
def cittadino(conn):
    """Inserisce un cittadino di prova e ne restituisce il citizen_id."""
    from anagrafe import repository

    return repository.insert_citizen(conn, 12345, "@mariorossi", "Mario", "Rossi")


@pytest.fixture
def attivita(conn, cittadino):
    """Iscrive un'attività di prova del `cittadino` e ne restituisce l'ID."""
    from anagrafe import repository

    return repository.create_attivita(
        conn,
        owner_id=12345,
        owner_username="mariorossi",
        nome_attivita="Pizzeria Da Mario",
        tipologia="privata",
        descrizione="Pizza al taglio, forno a legna.",
        contatto_link="@pizzeriadamario",
    )


@pytest.fixture
def proposta(conn, cittadino):
    """Una proposta di attività in attesa, del `cittadino` di prova."""
    from anagrafe import repository

    return repository.crea_proposta(
        conn,
        owner_id=12345,
        owner_username="mariorossi",
        nome_attivita="Bar Nuovo",
        tipologia="privata",
        descrizione="Caffè e cornetti.",
        contatto_link="@barnuovo",
    )
