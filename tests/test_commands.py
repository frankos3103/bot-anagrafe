"""Il registro dei comandi: filtro per ruolo, aiuto e menu nativo."""

import pytest

from anagrafe.commands import (
    COMMANDS,
    ETICHETTE_TIPOLOGIA,
    TIPOLOGIE_ATTIVITA,
    comandi_menu_telegram,
    comandi_per_ruolo,
    etichetta_tipologia,
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
    assert not visibili & {"inserisci", "rimuovi", "importa", "tagall"}
    assert not visibili & {"aggiungi_admin", "rimuovi_admin", "elenco_admin"}


def test_ladmin_vede_anche_i_comandi_admin():
    visibili = nomi(Role.ADMIN)
    assert {"inserisci", "rimuovi", "importa", "elenco", "tagall"} <= visibili
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


# ----------------------------------------------------------------------
# Campi a pulsanti
# ----------------------------------------------------------------------

def _campi_a_pulsanti():
    return [
        (comando, campo)
        for comando in COMMANDS
        for campo in comando.campi
        if campo.a_pulsanti
    ]


def test_ogni_opzione_passa_il_proprio_validatore():
    """La rete di sicurezza del wizard a pulsanti.

    Una scelta fatta col pulsante attraversa lo stesso validatore del testo: se
    un'opzione e il suo validatore si disallineassero, il pulsante salverebbe un
    valore che il validatore rifiuta. Questo test lo rende impossibile.
    """
    for comando, campo in _campi_a_pulsanti():
        for opzione in campo.opzioni:
            assert campo.validatore(opzione.chiave) == opzione.chiave, comando.nome
            assert campo.validatore(opzione.label) == opzione.chiave, comando.nome
            assert campo.validatore(opzione.etichetta) == opzione.chiave, comando.nome


def test_le_chiavi_delle_opzioni_sono_uniche():
    for comando, campo in _campi_a_pulsanti():
        chiavi = [o.chiave for o in campo.opzioni]
        assert len(chiavi) == len(set(chiavi)), f"{comando.nome}.{campo.chiave}"


def test_un_campo_a_pulsanti_offre_almeno_due_scelte():
    for comando, campo in _campi_a_pulsanti():
        assert len(campo.opzioni) >= 2, f"{comando.nome}.{campo.chiave}"


def test_il_callback_data_delle_opzioni_sta_nei_64_byte():
    """Telegram tronca oltre i 64 byte: per questo si usano gli indici."""
    for comando, campo in _campi_a_pulsanti():
        indice_campo = comando.campi.index(campo)
        for indice_opzione in range(len(campo.opzioni)):
            dato = f"menu:opt:{indice_campo}:{indice_opzione}"
            assert len(dato.encode()) <= 64, dato


def test_i_campi_senza_opzioni_non_sono_cambiati():
    senza = [
        campo
        for comando in COMMANDS
        for campo in comando.campi
        if not campo.a_pulsanti
    ]
    assert senza
    assert all(c.opzioni == () and c.per_riga == 1 for c in senza)


def test_il_riepilogo_mostra_letichetta_non_la_chiave():
    campo = trova_comando("attivita").campi[1]
    assert campo.mostra("privata") == "💼 Attività Privata"
    assert campo.mostra(None) == "(nessuno)"


# ----------------------------------------------------------------------
# Comandi con wizard diretto
# ----------------------------------------------------------------------

def _wizard_diretti():
    return [c for c in COMMANDS if c.wizard_diretto]


def test_un_wizard_diretto_ha_dei_campi():
    assert _wizard_diretti()
    assert all(c.richiede_input for c in _wizard_diretti())


def test_i_wizard_diretti_non_sono_fra_i_comandi_testuali():
    """Starebbero in COMANDI senza essere mai raggiunti.

    La ConversationHandler è registrata prima dei CommandHandler, quindi vince
    il suo entry point: un CommandHandler omonimo sarebbe un bug fantasma.
    """
    from anagrafe.handlers import COMANDI

    for comando in _wizard_diretti():
        assert comando.nome not in COMANDI, comando.nome


# ----------------------------------------------------------------------
# Registro delle attività
# ----------------------------------------------------------------------

def test_le_tipologie_sono_quelle_del_decreto():
    assert len(TIPOLOGIE_ATTIVITA) == 3
    assert set(ETICHETTE_TIPOLOGIA.values()) == {
        "Organizzazione",
        "Associazione",
        "Attività Privata",
    }


def test_ogni_tipologia_ha_unemoji_e_unetichetta():
    for opzione in TIPOLOGIE_ATTIVITA:
        assert opzione.emoji and opzione.etichetta
        assert opzione.label.endswith(opzione.etichetta)


def test_etichetta_di_una_tipologia_sconosciuta():
    assert etichetta_tipologia("inventata") == "inventata"


def test_i_comandi_del_registro_e_i_loro_ruoli():
    pubblici = nomi(Role.PUBBLICO)
    assert {"attivita", "elenco_attivita"} <= pubblici
    assert "modera_attivita" not in pubblici
    assert "modera_attivita" in nomi(Role.ADMIN)


def test_la_moderazione_non_sta_nel_menu_nativo():
    assert "modera_attivita" not in {n for n, _ in comandi_menu_telegram()}
