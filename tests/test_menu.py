"""Le funzioni pure della pulsantiera: impaginazione e callback_data.

Non si simula nessuna conversazione: si verificano solo i calcoli che decidono
quante pagine servono e che cosa finisce dentro ai pulsanti.
"""

import pytest

from anagrafe.commands import trova_comando
from anagrafe.handlers.menu import (
    SCELTE_PER_PAGINA,
    _pagine,
    _righe_impaginazione,
    _tastiera_campo,
)


def _dati(righe):
    return [b.callback_data for riga in righe for b in riga]


def _testi(tastiera):
    return [b.text for riga in tastiera.inline_keyboard for b in riga]


# ----------------------------------------------------------------------
# Quante pagine
# ----------------------------------------------------------------------

@pytest.mark.parametrize(
    "totale,attese",
    [
        (0, 1),  # una pagina vuota, non zero pagine
        (1, 1),
        (SCELTE_PER_PAGINA, 1),
        (SCELTE_PER_PAGINA + 1, 2),
        (SCELTE_PER_PAGINA * 3, 3),
        (SCELTE_PER_PAGINA * 3 + 1, 4),
    ],
)
def test_conteggio_delle_pagine(totale, attese):
    assert _pagine(totale) == attese


# ----------------------------------------------------------------------
# Le frecce
# ----------------------------------------------------------------------

def test_una_sola_pagina_non_ha_frecce():
    assert _righe_impaginazione(0, 0, SCELTE_PER_PAGINA) == []


def test_la_prima_pagina_non_ha_la_freccia_indietro():
    testi = [b.text for b in _righe_impaginazione(0, 0, 30)[0]]
    assert testi == ["1/4", "➡️"]


def test_la_pagina_in_mezzo_ha_entrambe_le_frecce():
    testi = [b.text for b in _righe_impaginazione(0, 1, 30)[0]]
    assert testi == ["⬅️", "2/4", "➡️"]


def test_lultima_pagina_non_ha_la_freccia_avanti():
    testi = [b.text for b in _righe_impaginazione(0, 3, 30)[0]]
    assert testi == ["⬅️", "4/4"]


def test_le_frecce_portano_lindice_del_campo_e_la_pagina():
    dati = _dati(_righe_impaginazione(2, 1, 30))
    assert dati == ["menu:pag:2:0", "menu:pag:2:1", "menu:pag:2:2"]


def test_il_callback_data_delle_pagine_sta_nei_64_byte():
    """Indici e non etichette: il limite è strutturalmente irraggiungibile."""
    for dato in _dati(_righe_impaginazione(9, 5, 10_000)):
        assert len(dato.encode()) <= 64, dato


# ----------------------------------------------------------------------
# La tastiera di un campo a scelte
# ----------------------------------------------------------------------

def _scelte(quante):
    return [[str(i), f"Voce {i}"] for i in range(quante)]


def _campo_a_scelte():
    return trova_comando("rimuovi_cittadino").campi[0]


def test_la_tastiera_mostra_una_pagina_per_volta():
    stato = {"indice": 0, "scelte": _scelte(30), "pagina": 0}
    testi = _testi(_tastiera_campo(stato, _campo_a_scelte()))
    voci = [t for t in testi if t.startswith("Voce ")]
    assert voci == [f"Voce {i}" for i in range(SCELTE_PER_PAGINA)]


def test_la_tastiera_di_una_pagina_successiva_riprende_da_dove_era():
    stato = {"indice": 0, "scelte": _scelte(30), "pagina": 2}
    testi = _testi(_tastiera_campo(stato, _campo_a_scelte()))
    voci = [t for t in testi if t.startswith("Voce ")]
    assert voci[0] == f"Voce {2 * SCELTE_PER_PAGINA}"


def test_i_pulsanti_portano_lindice_assoluto_non_quello_di_pagina():
    """È ciò che permette a on_opzione di risolvere la voce premuta.

    Con gli indici relativi alla pagina, premere il primo pulsante della
    seconda pagina avrebbe scelto la prima voce della lista.
    """
    stato = {"indice": 0, "scelte": _scelte(30), "pagina": 1}
    dati = _dati(_tastiera_campo(stato, _campo_a_scelte()).inline_keyboard)
    scelte = [d for d in dati if d.startswith("menu:opt:")]
    assert scelte[0] == f"menu:opt:0:{SCELTE_PER_PAGINA}"


def test_lultima_pagina_puo_essere_incompleta():
    stato = {"indice": 0, "scelte": _scelte(SCELTE_PER_PAGINA + 2), "pagina": 1}
    testi = _testi(_tastiera_campo(stato, _campo_a_scelte()))
    assert len([t for t in testi if t.startswith("Voce ")]) == 2


def test_un_campo_a_scelte_ha_sempre_annulla():
    stato = {"indice": 0, "scelte": _scelte(3), "pagina": 0}
    assert "❌ Annulla" in _testi(_tastiera_campo(stato, _campo_a_scelte()))


def test_la_tastiera_di_un_campo_a_opzioni_fisse_non_e_impaginata():
    """Le tipologie sono tre e si mostrano tutte."""
    campo = trova_comando("registra_attivita").campi[1]
    stato = {"indice": 1}
    dati = _dati(_tastiera_campo(stato, campo).inline_keyboard)
    assert not any(d.startswith("menu:pag:") for d in dati)
    assert len([d for d in dati if d.startswith("menu:opt:")]) == len(campo.opzioni)
