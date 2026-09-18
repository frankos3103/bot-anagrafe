"""Query sul registro: cittadini e richieste di cittadinanza."""

import pytest

from anagrafe import repository


def test_inserisci_e_rileggi(conn):
    citizen_id = repository.insert_citizen(conn, 12345, "@mariorossi", "Mario", "Rossi")
    riga = repository.get_citizen_by_telegram_id(conn, 12345)
    assert riga["citizen_id"] == citizen_id
    assert riga["username"] == "mariorossi"  # la @ viene tolta
    assert riga["nome"] == "Mario"


def test_username_vuoto_diventa_none(conn):
    repository.insert_citizen(conn, 12345, "", "Mario", "Rossi")
    assert repository.get_citizen_by_telegram_id(conn, 12345)["username"] is None


def test_telegram_id_duplicato_rifiutato(conn, cittadino):
    with pytest.raises(repository.CittadinoGiaEsistente) as info:
        repository.insert_citizen(conn, 12345, "@altro", "Luigi", "Bianchi")
    assert info.value.citizen_id == cittadino


def test_cittadino_inesistente(conn):
    assert repository.get_citizen_by_telegram_id(conn, 999) is None
    assert repository.get_citizen_by_citizen_id(conn, 999) is None


def test_rimozione(conn, cittadino):
    riga = repository.delete_citizen(conn, cittadino)
    assert riga["nome"] == "Mario"
    assert repository.get_citizen_by_citizen_id(conn, cittadino) is None


def test_rimozione_di_un_id_assente(conn):
    assert repository.delete_citizen(conn, 999) is None


def test_conteggio(conn):
    assert repository.count_citizens(conn) == 0
    repository.insert_citizen(conn, 1, None, "Mario", "Rossi")
    repository.insert_citizen(conn, 2, None, "Luigi", "Bianchi")
    assert repository.count_citizens(conn) == 2


def test_ordinamenti(conn):
    repository.insert_citizen(conn, 1, None, "Zeno", "Zeta")
    repository.insert_citizen(conn, 2, None, "Anna", "Alfa")

    per_id = [r["nome"] for r in repository.list_citizens(conn, ordine="citizen_id")]
    per_nome = [r["nome"] for r in repository.list_citizens(conn, ordine="nome")]
    assert per_id == ["Zeno", "Anna"]
    assert per_nome == ["Anna", "Zeno"]


# ----------------------------------------------------------------------
# Ricerca
# ----------------------------------------------------------------------

@pytest.fixture
def registro(conn):
    repository.insert_citizen(conn, 111, "@mariorossi", "Mario", "Rossi")
    repository.insert_citizen(conn, 222, "@lbianchi", "Luigi", "Bianchi")
    repository.insert_citizen(conn, 333, None, "Anna", "Verdi")
    return conn


@pytest.mark.parametrize(
    "query, attesi",
    [
        ("mario", ["Mario"]),
        ("MARIO", ["Mario"]),  # la ricerca ignora maiuscole e minuscole
        ("ross", ["Mario"]),
        ("bianchi", ["Luigi"]),
        ("lbianchi", ["Luigi"]),  # per username
        ("222", ["Luigi"]),  # per ID Telegram
        ("i", ["Mario", "Luigi", "Anna"]),  # sottostringa
        ("inesistente", []),
    ],
)
def test_ricerca(registro, query, attesi):
    trovati = [r["nome"] for r in repository.search_citizens(registro, query)]
    assert trovati == attesi


@pytest.mark.parametrize(
    "query, attesi",
    [
        ("Mario Rossi", ["Mario"]),  # informazioni aggregate
        ("rossi mario", ["Mario"]),  # in qualunque ordine
        ("Mario, Rossi", ["Mario"]),
        ("mario bianchi", []),  # ogni parola deve comparire
        ("@lbianchi", ["Luigi"]),
        ("@bianchi", ["Luigi"]),  # parte del tag
        ("@anna", []),  # la @ cerca solo fra i tag
        ("#3", ["Anna"]),
        ("#33", []),
        ("anna 333", ["Anna"]),  # nome + ID Telegram
    ],
)
def test_ricerca_per_parole(registro, query, attesi):
    trovati = [r["nome"] for r in repository.search_citizens(registro, query)]
    assert trovati == attesi


def test_ricerca_ignora_gli_accenti(conn):
    repository.insert_citizen(conn, 1, None, "Nicolò", "Débora")
    assert [r["nome"] for r in repository.search_citizens(conn, "nicolo debora")] == ["Nicolò"]
    assert [r["nome"] for r in repository.search_citizens(conn, "NICOLÒ")] == ["Nicolò"]


def test_ricerca_mette_prima_i_risultati_esatti(conn):
    repository.insert_citizen(conn, 1, None, "Marianna", "Rossini")
    repository.insert_citizen(conn, 2, None, "Mario", "Rossi")
    trovati = [r["nome"] for r in repository.search_citizens(conn, "mario rossi")]
    assert trovati == ["Mario"]
    trovati = [r["nome"] for r in repository.search_citizens(conn, "mari ross")]
    assert trovati == ["Marianna", "Mario"]  # a parità di punteggio, ordine di ID
    trovati = [r["nome"] for r in repository.search_citizens(conn, "rossi")]
    assert trovati == ["Mario", "Marianna"]  # parola intera prima del prefisso


@pytest.mark.parametrize(
    "query, attesi",
    [
        ("Mairo Rosi", ["Mario"]),
        ("biachi", ["Luigi"]),
        ("verdy", ["Anna"]),
        ("zzzzz", []),
        ("xy", []),  # troppo corto per tentare
    ],
)
def test_suggerimenti_tolleranti_ai_refusi(registro, query, attesi):
    trovati = [r["nome"] for r in repository.suggest_citizens(registro, query)]
    assert trovati == attesi


def test_cittadini_per_username(registro):
    assert [r["nome"] for r in repository.get_citizens_by_username(registro, "@MarioRossi")] == [
        "Mario"
    ]
    assert repository.get_citizens_by_username(registro, "nessuno") == []


# ----------------------------------------------------------------------
# Username automatico
# ----------------------------------------------------------------------

def test_update_username_cambia(conn, cittadino):
    esito = repository.update_username(conn, 12345, "nuovo_nick")
    assert esito is not None
    assert esito.riga["username"] == "mariorossi"
    assert esito.nuovo == "nuovo_nick"
    assert esito.sottratto_a == []
    assert repository.get_citizen_by_telegram_id(conn, 12345)["username"] == "nuovo_nick"


def test_update_username_toglie_il_tag_a_chi_lo_aveva_prima(conn, cittadino):
    """Un tag appartiene a un solo utente: chi lo usa ora ne è il titolare."""
    altro = repository.insert_citizen(conn, 999, "vecchio", "Luigi", "Bianchi")
    esito = repository.update_username(conn, 999, "MarioRossi")

    assert [r["citizen_id"] for r in esito.sottratto_a] == [cittadino]
    assert repository.get_citizen_by_citizen_id(conn, cittadino)["username"] is None
    assert repository.get_citizen_by_citizen_id(conn, altro)["username"] == "MarioRossi"


def test_update_username_di_un_non_cittadino_libera_il_tag(conn, cittadino):
    esito = repository.update_username(conn, 999, "mariorossi")
    assert esito.riga is None
    assert [r["citizen_id"] for r in esito.sottratto_a] == [cittadino]
    assert repository.get_citizen_by_citizen_id(conn, cittadino)["username"] is None


def test_update_username_invariato_e_un_nonnulla(conn, cittadino):
    assert repository.update_username(conn, 12345, "@mariorossi") is None


def test_update_username_di_un_non_cittadino(conn):
    assert repository.update_username(conn, 999, "chiunque") is None


def test_update_username_rimosso(conn, cittadino):
    esito = repository.update_username(conn, 12345, None)
    assert esito is not None
    assert repository.get_citizen_by_telegram_id(conn, 12345)["username"] is None


# ----------------------------------------------------------------------
# Richieste
# ----------------------------------------------------------------------

def test_ciclo_di_vita_di_una_richiesta(conn):
    request_id = repository.create_request(conn, 555, "@aspirante", "Carlo", "Neri")

    in_attesa = repository.pending_request_for(conn, 555)
    assert in_attesa["request_id"] == request_id
    assert in_attesa["stato"] == repository.STATO_IN_ATTESA

    repository.resolve_request(conn, request_id, repository.STATO_ACCETTATA, 100, "@capo")

    assert repository.pending_request_for(conn, 555) is None
    risolta = repository.get_request(conn, request_id)
    assert risolta["stato"] == repository.STATO_ACCETTATA
    assert risolta["admin_id"] == 100
    assert risolta["admin_username"] == "capo"
    assert risolta["data_gestione"]


def test_notifiche_salvate_e_rilette(conn):
    request_id = repository.create_request(conn, 555, None, "Carlo", "Neri")
    repository.set_request_notifications(conn, request_id, [[10, 1], [20, 2]])
    riga = repository.get_request(conn, request_id)
    assert repository.load_request_notifications(riga["notifiche"]) == [(10, 1), (20, 2)]


@pytest.mark.parametrize("grezzo", [None, "", "non-json", "[[1]]", '"stringa"'])
def test_notifiche_corrotte_non_esplodono(grezzo):
    assert repository.load_request_notifications(grezzo) == []
