"""Il registro dei comandi: filtro per ruolo, aiuto e menu nativo."""

import pytest

from anagrafe.commands import (
    COMMANDS,
    ETICHETTE_TIPOLOGIA,
    SEZIONI,
    TIPOLOGIE_ATTIVITA,
    comandi_menu_telegram,
    comandi_per_ruolo,
    etichetta_tipologia,
    render_help,
    render_uso,
    sezioni_per_ruolo,
    trova_comando,
    trova_sezione,
)
from anagrafe.roles import Role


def nomi(ruolo, solo_menu=False):
    return {c.nome for c in comandi_per_ruolo(ruolo, solo_menu=solo_menu)}


def test_il_pubblico_non_vede_i_comandi_riservati():
    visibili = nomi(Role.PUBBLICO)
    assert {"elenco_cittadini", "esporta_cittadini", "cerca_cittadino", "richiedi_cittadinanza", "help", "menu"} <= visibili
    assert not visibili & {"inserisci_cittadino", "rimuovi_cittadino", "importa_cittadini", "tagga_cittadini"}
    assert not visibili & {"aggiungi_admin", "rimuovi_admin", "elenco_admin"}


def test_ladmin_vede_anche_i_comandi_admin():
    visibili = nomi(Role.ADMIN)
    assert {"inserisci_cittadino", "rimuovi_cittadino", "importa_cittadini", "elenco_cittadini", "tagga_cittadini"} <= visibili
    assert not visibili & {"aggiungi_admin", "rimuovi_admin", "elenco_admin"}


def test_il_root_vede_tutto():
    visibili = nomi(Role.ROOT)
    assert {"aggiungi_admin", "rimuovi_admin", "elenco_admin", "inserisci_cittadino"} <= visibili


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
    assert "/elenco_cittadini" in testo
    assert "/inserisci_cittadino" not in testo
    assert "/aggiungi_admin" not in testo
    assert "Comandi amministratore" not in testo


def test_aiuto_admin():
    testo = render_help(Role.ADMIN)
    assert "/elenco_cittadini" in testo
    assert "/inserisci_cittadino" in testo
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
        assert comando.nome in AZIONI or comando.attende_allegato


def test_nessuna_chiave_orfana_nei_dizionari_dei_comandi():
    """Ogni chiave che nomina un comando deve nominarne uno che esiste.

    I comandi sono indicizzati per nome in quattro dizionari diversi. Una chiave
    rimasta con un nome vecchio, o scritta male, non darebbe alcun errore:
    resterebbe soltanto morta, e il comando non risponderebbe. È la rete che
    rende sicuro rinominare un comando.
    """
    from anagrafe.handlers import COMANDI
    from anagrafe.handlers.azioni import AZIONI
    from anagrafe.handlers.controlli import PRECONDIZIONI, VERIFICHE_CAMPO

    for etichetta, dizionario in (
        ("COMANDI", COMANDI),
        ("AZIONI", AZIONI),
        ("PRECONDIZIONI", PRECONDIZIONI),
    ):
        for nome in dizionario:
            assert trova_comando(nome) is not None, f"{etichetta}: «{nome}»"

    # VERIFICHE_CAMPO è indicizzata per (comando, campo): vanno verificati entrambi.
    for nome, chiave_campo in VERIFICHE_CAMPO:
        comando = trova_comando(nome)
        assert comando is not None, f"VERIFICHE_CAMPO: «{nome}»"
        chiavi = {campo.chiave for campo in comando.campi}
        assert chiave_campo in chiavi, f"VERIFICHE_CAMPO: «{nome}» non ha il campo «{chiave_campo}»"


def test_trova_comando():
    assert trova_comando("elenco_cittadini").nome == "elenco_cittadini"
    assert trova_comando("inesistente") is None


def test_render_uso_include_lesempio():
    testo = render_uso(trova_comando("inserisci_cittadino"))
    assert "/inserisci_cittadino" in testo
    assert "Esempio" in testo


def test_menu_nativo_solo_pubblico():
    nomi_menu = {nome for nome, _ in comandi_menu_telegram()}
    assert nomi_menu <= nomi(Role.PUBBLICO)
    assert "inserisci_cittadino" not in nomi_menu
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
    campo = trova_comando("registra_attivita").campi[1]
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
    assert {"registra_attivita", "elenco_attivita"} <= pubblici
    assert "modera_attivita" not in pubblici
    assert "modera_attivita" in nomi(Role.ADMIN)


def test_la_moderazione_non_sta_nel_menu_nativo():
    assert "modera_attivita" not in {n for n, _ in comandi_menu_telegram()}


# ----------------------------------------------------------------------
# Sezioni della pulsantiera
# ----------------------------------------------------------------------

def test_ogni_comando_del_menu_ha_una_sezione():
    """Un pulsante senza area sarebbe irraggiungibile dalla pulsantiera.

    Comparirebbe in /help ma in nessuna delle viste, perché queste elencano i
    comandi sezione per sezione.
    """
    for comando in comandi_per_ruolo(Role.ROOT, solo_menu=True):
        assert trova_sezione(comando.sezione) is not None, comando.nome


def test_i_comandi_fuori_dalla_pulsantiera_non_hanno_sezione():
    for comando in COMMANDS:
        if not comando.nel_menu:
            assert comando.sezione == "", comando.nome


def test_ogni_sezione_ha_almeno_un_comando():
    """Nessuna sezione decorativa: mostrerebbe una tastiera vuota."""
    for sezione in SEZIONI:
        comandi = comandi_per_ruolo(Role.ROOT, solo_menu=True, sezione=sezione.chiave)
        assert comandi, sezione.chiave


def test_le_chiavi_delle_sezioni_sono_uniche():
    chiavi = [s.chiave for s in SEZIONI]
    assert len(chiavi) == len(set(chiavi))


def test_le_sezioni_visibili_crescono_col_ruolo():
    pubblico = sezioni_per_ruolo(Role.PUBBLICO)
    root = sezioni_per_ruolo(Role.ROOT)
    assert [s.chiave for s in pubblico] == ["cittadini", "attivita"]
    assert [s.chiave for s in root] == ["cittadini", "attivita", "amministrazione"]


def test_un_cittadino_non_vede_lamministrazione():
    assert "amministrazione" not in {s.chiave for s in sezioni_per_ruolo(Role.PUBBLICO)}
    assert not comandi_per_ruolo(
        Role.PUBBLICO, solo_menu=True, sezione="amministrazione"
    )


def test_i_comandi_di_una_sezione_sono_filtrati_per_ruolo():
    """La sezione dice di cosa si parla, il ruolo dice chi può: sono ortogonali."""
    pubblici = comandi_per_ruolo(Role.PUBBLICO, solo_menu=True, sezione="cittadini")
    admin = comandi_per_ruolo(Role.ADMIN, solo_menu=True, sezione="cittadini")
    assert {c.nome for c in pubblici} < {c.nome for c in admin}
    # I comandi admin sui cittadini stanno in «Cittadinanza», non in «Amministrazione».
    assert "inserisci_cittadino" in {c.nome for c in admin}


def test_una_sezione_inesistente_non_si_trova():
    assert trova_sezione("inventata") is None
    assert trova_sezione("") is None


def test_la_somma_delle_sezioni_e_tutta_la_pulsantiera():
    """Nessun comando resta fuori da tutte le viste."""
    tutti = {c.nome for c in comandi_per_ruolo(Role.ROOT, solo_menu=True)}
    per_sezione = {
        c.nome
        for s in SEZIONI
        for c in comandi_per_ruolo(Role.ROOT, solo_menu=True, sezione=s.chiave)
    }
    assert tutti == per_sezione


# ----------------------------------------------------------------------
# Campi con scelte lette dal registro
# ----------------------------------------------------------------------

def _campi_a_scelte():
    return [
        (comando, campo)
        for comando in COMMANDS
        for campo in comando.campi
        if campo.a_scelte
    ]


def test_ogni_campo_a_scelte_ha_il_suo_fornitore():
    """Senza fornitore il wizard non avrebbe nulla da mostrare e si bloccherebbe."""
    from anagrafe.handlers.scelte import FORNITORI

    assert _campi_a_scelte()
    for comando, campo in _campi_a_scelte():
        assert campo.scelte in FORNITORI, f"{comando.nome}.{campo.chiave}"


def test_nessun_fornitore_resta_inutilizzato():
    """Un fornitore che nessun campo richiama sarebbe codice morto."""
    from anagrafe.handlers.scelte import FORNITORI

    richiamati = {campo.scelte for _, campo in _campi_a_scelte()}
    assert set(FORNITORI) == richiamati


def test_un_campo_a_scelte_dice_cosa_fare_quando_e_vuoto():
    """Senza il messaggio il bot direbbe soltanto «non c'è nulla da scegliere»."""
    for comando, campo in _campi_a_scelte():
        assert campo.messaggio_vuoto, f"{comando.nome}.{campo.chiave}"


def test_un_campo_non_ha_sia_opzioni_fisse_sia_scelte():
    """Sono due modi alternativi di riempire la stessa tastiera."""
    for comando in COMMANDS:
        for campo in comando.campi:
            assert not (campo.a_pulsanti and campo.a_scelte), (
                f"{comando.nome}.{campo.chiave}"
            )


def test_nessun_comando_chiede_piu_un_id_a_mano():
    """La ragione di questo lavoro: rimozione e moderazione a pulsanti.

    Se un giorno uno di questi campi perdesse il suo fornitore, tornerebbe a
    farsi digitare un ID numerico senza che nessuno se ne accorga.
    """
    a_scelte = {(c.nome, campo.chiave) for c, campo in _campi_a_scelte()}
    assert {
        ("rimuovi_cittadino", "cittadino"),
        ("rimuovi_attivita", "attivita"),
        ("modera_attivita", "attivita"),
        ("aggiungi_admin", "utente"),
        ("rimuovi_admin", "utente"),
    } <= a_scelte


# ----------------------------------------------------------------------
# Export e import
# ----------------------------------------------------------------------

def test_i_comandi_con_allegato_hanno_una_voce_di_import():
    """Senza, il bot chiederebbe un file che poi non saprebbe dove mettere."""
    from anagrafe.handlers.importazione import IMPORTAZIONI

    con_allegato = {c.nome for c in COMMANDS if c.attende_allegato}
    assert con_allegato
    assert con_allegato == set(IMPORTAZIONI)


def test_ogni_voce_di_import_nomina_un_comando_con_allegato():
    from anagrafe.handlers.importazione import IMPORTAZIONI

    for nome, voce in IMPORTAZIONI.items():
        comando = trova_comando(nome)
        assert comando is not None, nome
        assert comando.attende_allegato, nome
        assert voce.comando == nome
        assert voce.istruzioni.strip()


def test_un_comando_con_allegato_non_chiede_dati_al_wizard():
    """L'allegato e il wizard sono due modi alternativi di completare."""
    for comando in COMMANDS:
        if comando.attende_allegato:
            assert not comando.richiede_input, comando.nome


def test_senza_conferma_serve_solo_a_chi_raccoglie_dati():
    for comando in COMMANDS:
        if comando.senza_conferma:
            assert comando.richiede_input, comando.nome


def test_gli_export_chiedono_il_formato_e_non_la_conferma():
    """Un export è di sola lettura: il riepilogo sarebbe un click in più."""
    for nome in ("esporta_cittadini", "esporta_attivita"):
        comando = trova_comando(nome)
        assert comando is not None, nome
        assert [c.chiave for c in comando.campi] == ["formato"]
        assert comando.senza_conferma, nome
        assert comando.campi[0].a_pulsanti


def test_i_due_formati_sono_md_e_csv():
    from anagrafe.commands import FORMATI_EXPORT

    assert {o.chiave for o in FORMATI_EXPORT} == {"md", "csv"}


def test_i_registri_hanno_tutti_export_e_import():
    """Issue #46: le attività devono avere lo stesso corredo dei cittadini."""
    nomi = {c.nome for c in COMMANDS}
    assert {"esporta_cittadini", "importa_cittadini"} <= nomi
    assert {"esporta_attivita", "importa_attivita"} <= nomi
