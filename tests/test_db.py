"""Schema del registro: creazione, idempotenza, indici, migrazione implicita."""

from anagrafe import repository
from anagrafe.db import SCHEMA_CITTADINI, SCHEMA_RICHIESTE, get_connection, init_db


def _tabelle(conn):
    return {
        r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }


def _indici(conn, tabella):
    return {r["name"] for r in conn.execute(f"PRAGMA index_list('{tabella}')")}


def test_init_db_crea_le_tre_tabelle(conn):
    assert {"cittadini", "richieste", "attivita"} <= _tabelle(conn)


def test_init_db_e_idempotente(db_path):
    """Si chiama a ogni avvio: rieseguirla non deve sollevare."""
    init_db(db_path)
    init_db(db_path)


def test_le_attivita_hanno_i_loro_indici(conn):
    assert {
        "idx_attivita_stato",
        "idx_attivita_owner",
        "idx_attivita_nome_owner",
    } <= _indici(conn, "attivita")


def test_migrazione_di_un_registro_preesistente(tmp_path):
    """Un registro.db con le sole tabelle vecchie acquisisce «attivita»."""
    percorso = tmp_path / "vecchio.db"
    vecchio = get_connection(percorso)
    vecchio.execute(SCHEMA_CITTADINI)
    vecchio.execute(SCHEMA_RICHIESTE)
    vecchio.commit()
    assert "attivita" not in _tabelle(vecchio)
    vecchio.close()

    init_db(percorso)

    conn = get_connection(percorso)
    try:
        assert "attivita" in _tabelle(conn)
    finally:
        conn.close()


# ----------------------------------------------------------------------
# La foreign key assente è una decisione, non una dimenticanza
# ----------------------------------------------------------------------

def test_i_vincoli_di_chiave_esterna_sono_attivi(conn):
    """Il presupposto di test_nessuna_foreign_key_su_attivita."""
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_nessuna_foreign_key_su_attivita(conn):
    """owner_id non è una FK verso cittadini(telegram_id).

    Quella colonna non è la primary key e il suo indice unico può mancare sui
    registri con ID Telegram duplicati: con i vincoli attivi, una FK verso una
    colonna non unica farebbe fallire ogni INSERT con «foreign key mismatch»,
    e senza ON DELETE bloccherebbe /rimuovi. Il vincolo di cittadinanza è
    applicato in controlli.precondizione_attivita.
    """
    assert conn.execute("PRAGMA foreign_key_list('attivita')").fetchall() == []


def test_si_puo_iscrivere_anche_senza_il_cittadino(conn):
    """Conseguenza accettata: nessun errore a livello di database."""
    attivita_id = repository.create_attivita(
        conn, 99999, None, "Attività orfana", "privata", "Nessun cittadino."
    )
    assert repository.get_attivita(conn, attivita_id)["owner_id"] == 99999


def test_rimuovere_un_cittadino_con_attivita_funziona(conn, cittadino, attivita):
    """Una FK con RESTRICT implicito avrebbe rotto /rimuovi."""
    riga = repository.delete_citizen(conn, cittadino)
    assert riga is not None
    assert repository.get_attivita(conn, attivita) is not None
