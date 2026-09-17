"""Il registro dei comandi: filtro per ruolo, aiuto e menu nativo."""

import pytest

from anagrafe.commands import (
    COMMANDS,
    comandi_menu_telegram,
    comandi_per_ruolo,
    render_help,
    render_uso,
    trova_comando,
)
from anagrafe.roles import Role


def nomi(ruolo, solo_menu=False):
    return {c.nome for c in comandi_per_ruolo(ruolo, solo_menu=solo_menu)}


def test_il_pubblico_non_vede_i_comandi_riservati():
    visibili = nomi(Role.PUBBLICO)
    assert {"elenco", "esporta", "cerca", "richiedi", "help", "menu"} <= visibili
    assert not visibili & {"inserisci", "rimuovi", "importa"}
    assert not visibili & {"aggiungi_admin", "rimuovi_admin", "elenco_admin"}


def test_ladmin_vede_anche_i_comandi_admin():
    visibili = nomi(Role.ADMIN)
    assert {"inserisci", "rimuovi", "importa", "elenco"} <= visibili
    assert not visibili & {"aggiungi_admin", "rimuovi_admin", "elenco_admin"}


def test_il_root_vede_tutto():
    visibili = nomi(Role.ROOT)
    assert {"aggiungi_admin", "rimuovi_admin", "elenco_admin", "inserisci"} <= visibili


def test_i_ruoli_sono_cumulativi():
    assert nomi(Role.PUBBLICO) < nomi(Role.ADMIN) < nomi(Role.ROOT)


def test_start_resta_fuori_da_aiuto_e_menu():
    assert "start" not in nomi(Role.ROOT)
    assert "start" not in nomi(Role.ROOT, solo_menu=True)


def test_help_e_menu_non_sono_pulsanti():
    """Sarebbe ridondante: la pulsantiera è già aperta."""
    pulsanti = nomi(Role.ROOT, solo_menu=True)
    assert "help" not in pulsanti
    assert "menu" not in pulsanti


# ----------------------------------------------------------------------
# Testo dell'aiuto
# ----------------------------------------------------------------------

def test_aiuto_pubblico():
    testo = render_help(Role.PUBBLICO)
    assert "/elenco" in testo
    assert "/inserisci" not in testo
    assert "/aggiungi_admin" not in testo
    assert "Comandi amministratore" not in testo


def test_aiuto_admin():
    testo = render_help(Role.ADMIN)
    assert "/elenco" in testo
    assert "/inserisci" in testo
    assert "Comandi amministratore" in testo
    assert "/aggiungi_admin" not in testo
    assert "Comandi root" not in testo


def test_aiuto_root():
    testo = render_help(Role.ROOT)
    assert "/aggiungi_admin" in testo
    assert "Comandi root" in testo


@pytest.mark.parametrize("ruolo", list(Role))
def test_laiuto_rimanda_sempre_al_menu(ruolo):
    assert "/menu" in render_help(ruolo)


@pytest.mark.parametrize("ruolo", list(Role))
def test_ogni_comando_visibile_compare_nellaiuto(ruolo):
    testo = render_help(ruolo)
    for comando in comandi_per_ruolo(ruolo):
        assert f"/{comando.nome}" in testo


# ----------------------------------------------------------------------
# Coerenza del registro
# ----------------------------------------------------------------------

def test_nomi_unici():
    assert len({c.nome for c in COMMANDS}) == len(COMMANDS)


def test_ogni_uso_inizia_con_lo_slash():
    assert all(c.uso.startswith(f"/{c.nome}") for c in COMMANDS)


def test_i_campi_del_wizard_hanno_chiavi_uniche():
    for comando in COMMANDS:
        chiavi = [campo.chiave for campo in comando.campi]
        assert len(chiavi) == len(set(chiavi)), comando.nome


def test_ogni_comando_del_menu_e_eseguibile():
    """Ogni pulsante deve avere un'azione dietro, o un caso speciale gestito."""
    from anagrafe.handlers.azioni import AZIONI

    for comando in comandi_per_ruolo(Role.ROOT, solo_menu=True):
        assert comando.nome in AZIONI or comando.nome == "importa"


def test_trova_comando():
    assert trova_comando("elenco").nome == "elenco"
    assert trova_comando("inesistente") is None


def test_render_uso_include_lesempio():
    testo = render_uso(trova_comando("inserisci"))
    assert "/inserisci" in testo
    assert "Esempio" in testo


def test_menu_nativo_solo_pubblico():
    nomi_menu = {nome for nome, _ in comandi_menu_telegram()}
    assert nomi_menu <= nomi(Role.PUBBLICO)
    assert "inserisci" not in nomi_menu
    assert all(descrizione for _, descrizione in comandi_menu_telegram())
