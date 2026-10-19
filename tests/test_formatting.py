"""Formattazione dei messaggi: escape, righe e impaginazione."""

import pytest

from anagrafe.formatting import (
    LIMITE_MESSAGGIO,
    SPAZIO_LARGHEZZA_ZERO,
    contatto_visibile,
    escape_markdown_legacy,
    escape_markdown_v2,
    escape_tabella,
    format_row,
    post_gazzetta,
    post_gazzetta_rimosso,
    riga_attivita,
    riga_elenco,
    scheda_moderazione,
    spezza_in_blocchi,
    username_o_placeholder,
    username_senza_tag,
)


def riga(citizen_id=1, telegram_id=111, username="mariorossi", nome="Mario", cognome="Rossi"):
    return {
        "citizen_id": citizen_id,
        "telegram_id": telegram_id,
        "username": username,
        "nome": nome,
        "cognome": cognome,
    }


def test_format_row_con_username():
    assert format_row(riga()) == f"#1 — 111 — Mario ROSSI (@{SPAZIO_LARGHEZZA_ZERO}mariorossi)"


def test_format_row_senza_username():
    assert format_row(riga(username=None)) == "#1 — 111 — Mario ROSSI (nessuno username)"


def test_format_row_non_tagga_nessuno():
    # Niente "@" seguito subito dallo username: Telegram non deve riconoscerlo
    # come menzione e notificare la persona.
    assert "@mariorossi" not in format_row(riga())


def test_username_o_placeholder():
    """Tag vero e proprio: usato solo da /tagga_cittadini."""
    assert username_o_placeholder("tizio") == "@tizio"
    assert username_o_placeholder(None) == "(nessuno username)"


def test_username_senza_tag():
    assert username_senza_tag("tizio") == f"@{SPAZIO_LARGHEZZA_ZERO}tizio"
    assert username_senza_tag(None) == "(nessuno username)"


@pytest.mark.parametrize(
    "grezzo, atteso",
    [
        ("Mario_Rossi", r"Mario\_Rossi"),
        ("D'Angelo-Neri", r"D'Angelo\-Neri"),
        ("100% (ok).", r"100% \(ok\)\."),
        (None, ""),
    ],
)
def test_escape_markdown_v2(grezzo, atteso):
    assert escape_markdown_v2(grezzo) == atteso


def test_escape_tabella():
    assert escape_tabella("a|b") == r"a\|b"
    assert escape_tabella("a\nb") == "a b"


@pytest.mark.parametrize("cognome", ["Zaccaria", "ZACCARIA", "zaccaria", "zAcCaRiA"])
def test_il_cognome_negli_elenchi_e_sempre_maiuscolo(cognome):
    dati = riga(nome="Giovanni", cognome=cognome)
    assert "*Giovanni ZACCARIA*" in riga_elenco(dati)
    assert "Giovanni ZACCARIA" in format_row(dati)


def test_cognome_accentato_in_maiuscolo():
    assert "ERÉSIA" in format_row(riga(cognome="Erésia"))


def test_riga_elenco_sfugge_i_caratteri_speciali():
    prodotta = riga_elenco(riga(nome="Gian_Luca", cognome="De-Rossi", username=None))
    assert r"Gian\_Luca" in prodotta
    assert r"DE\-ROSSI" in prodotta
    assert "nessuno username" in prodotta


def test_riga_elenco_non_tagga_nessuno():
    prodotta = riga_elenco(riga(username="mariorossi"))
    assert "@mariorossi" not in prodotta
    assert f"@{SPAZIO_LARGHEZZA_ZERO}mariorossi" in prodotta


# ----------------------------------------------------------------------
# Impaginazione
# ----------------------------------------------------------------------

def test_poche_righe_stanno_in_un_blocco():
    blocchi = spezza_in_blocchi(["a", "b", "c"], "Titolo")
    assert blocchi == ["Titolo\na\nb\nc"]


def test_nessuna_riga():
    assert spezza_in_blocchi([], "Titolo") == ["Titolo"]
    assert spezza_in_blocchi([]) == []


def test_molti_cittadini_vengono_spezzati():
    righe = [f"• Cittadino numero {i} con un nome piuttosto lungo" for i in range(500)]
    blocchi = spezza_in_blocchi(righe, "Titolo")

    assert len(blocchi) > 1
    assert all(len(b) <= LIMITE_MESSAGGIO for b in blocchi)

    # Nessuna riga persa e nessuna duplicata.
    ricomposto = "\n".join(blocchi).split("\n")
    assert ricomposto[0] == "Titolo"
    assert ricomposto[1:] == righe


def test_intestazione_solo_nel_primo_blocco():
    righe = [f"riga {i}" for i in range(500)]
    blocchi = spezza_in_blocchi(righe, "Titolo", limite=100)
    assert blocchi[0].startswith("Titolo")
    assert not any(b.startswith("Titolo") for b in blocchi[1:])


def test_riga_piu_lunga_del_limite_viene_troncata():
    blocchi = spezza_in_blocchi(["x" * 500], limite=100)
    assert len(blocchi) == 1
    assert len(blocchi[0]) <= 100
    assert blocchi[0].endswith("…")


# ----------------------------------------------------------------------
# Registro delle attività
# ----------------------------------------------------------------------

def attivita(**modifiche):
    riga = {
        "attivita_id": 7,
        "owner_id": 12345,
        "owner_username": "mariorossi",
        "nome_attivita": "Pizzeria Da Mario",
        "tipologia": "privata",
        "descrizione": "Pizza al taglio, forno a legna.",
        "contatto_link": "@pizzeriadamario",
        "stato": "ATTIVA",
        "created_at": "2026-10-18",
        "admin_id": None,
        "admin_username": None,
        "data_moderazione": None,
    }
    riga.update(modifiche)
    return riga


# Un nome che prova a iniettare un link nel post pubblico.
OSTILE = "Bar [clicca](http://spam.it)"


def test_il_post_sfugge_liniezione_di_link():
    testo = post_gazzetta(attivita(nome_attivita=OSTILE))
    # Nessuna parentesi quadra chiusa seguita da tonda aperta non sfuggita:
    # sarebbe un link cliccabile scritto dall'utente.
    assert "](" not in testo.replace("\\](", "")


@pytest.mark.parametrize("carattere", list("_*[]().!-"))
def test_il_post_sfugge_ogni_metacarattere_dellutente(carattere):
    """I marcatori del grassetto sono voluti; i caratteri dell'utente no.

    Si verifica quindi che il carattere scritto dall'utente compaia nella forma
    sfuggita, non che il messaggio sia privo di marcatori.
    """
    testo = post_gazzetta(attivita(descrizione=f"Prezzi {carattere} ottimi"))
    assert "\\" + carattere in testo


def test_il_post_senza_contatto_non_mostra_la_riga():
    assert "📞" not in post_gazzetta(attivita(contatto_link=None))
    assert "📞" in post_gazzetta(attivita())


def test_il_post_cita_lid_e_la_data():
    testo = post_gazzetta(attivita())
    assert "7" in testo and "2026" in testo


def test_un_post_al_massimo_della_descrizione_sta_nel_limite():
    testo = post_gazzetta(attivita(descrizione="x" * 500))
    assert len(testo) < LIMITE_MESSAGGIO


def test_la_pietra_tombale_cita_il_nome_e_il_decreto():
    testo = post_gazzetta_rimosso(attivita())
    assert "Pizzeria Da Mario" in testo
    assert "13/10/2026" in testo


def test_la_riga_dellelenco_non_tagga_nessuno():
    """Come /elenco_cittadini: un elenco non deve notificare cinquanta persone."""
    assert SPAZIO_LARGHEZZA_ZERO in riga_attivita(attivita())


def test_la_riga_dellelenco_senza_contatto():
    testo = riga_attivita(attivita(contatto_link=None))
    assert "nessun contatto" in testo


def test_la_riga_dellelenco_mostra_letichetta_della_tipologia():
    assert "Attività Privata" in riga_attivita(attivita())


def test_nella_gazzetta_il_tag_e_un_tag_vero():
    """Nel post pubblico la menzione è il punto, non un effetto collaterale."""
    assert SPAZIO_LARGHEZZA_ZERO not in post_gazzetta(attivita())


def test_la_scheda_admin_non_ha_bisogno_di_escape():
    """Va inviata senza parse_mode: il testo dell'utente resta tale e quale."""
    testo = scheda_moderazione(attivita(nome_attivita=OSTILE), {"username": "mariorossi", "citizen_id": 3})
    assert OSTILE in testo
    assert "cittadino #3" in testo


def test_la_scheda_admin_segnala_il_proprietario_sparito():
    testo = scheda_moderazione(attivita(), None)
    assert "non risulta iscritto" in testo


def test_la_scheda_admin_di_unattivita_moderata():
    testo = scheda_moderazione(
        attivita(stato="RIMOSSA", data_moderazione="2026-10-19",
                 admin_id=100, admin_username="capo"),
        None,
    )
    assert "RIMOSSA" in testo
    assert "2026-10-19" in testo
    assert "Ministero dell'Interno" not in testo  # niente invito a moderare


def test_la_scheda_admin_attiva_invita_a_moderare():
    testo = scheda_moderazione(attivita(), None)
    assert "Ministero dell'Interno" in testo


@pytest.mark.parametrize(
    "contatto,atteso",
    [
        (None, "(nessun contatto)"),
        ("", "(nessun contatto)"),
        ("https://t.me/x", "https://t.me/x"),
    ],
)
def test_contatto_visibile(contatto, atteso):
    assert contatto_visibile(contatto) == atteso


def test_un_elenco_lungo_resta_impaginato():
    blocchi = spezza_in_blocchi([riga_attivita(attivita())] * 300, "intestazione")
    assert len(blocchi) > 1
    assert all(len(b) <= LIMITE_MESSAGGIO for b in blocchi)


@pytest.mark.parametrize("carattere", list("_*`["))
def test_lescape_legacy_copre_i_caratteri_di_send_log(carattere):
    """send_log usa il Markdown «legacy» e non solleva: un log perso è invisibile."""
    assert escape_markdown_legacy(f"Bar{carattere}Mario") == f"Bar\\{carattere}Mario"


def test_lescape_legacy_di_none():
    assert escape_markdown_legacy(None) == ""
