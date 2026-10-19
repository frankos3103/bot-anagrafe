"""I fornitori di scelte: le voci che la pulsantiera legge dal registro.

Qui non si tocca Telegram: ai fornitori si passano soltanto i due oggetti che
il bot mette in `bot_data` (le impostazioni e il registro dei ruoli) e l'ID di
chi sta chiedendo. Le funzioni sono asincrone, quindi si eseguono con
`asyncio.run`: pytest-asyncio non è fra le dipendenze dichiarate del progetto.
"""

import asyncio
from types import SimpleNamespace

from anagrafe import controlli, repository
from anagrafe.commands import COMMANDS
from anagrafe.handlers import scelte as fornitori_scelte
from anagrafe.roles import RoleRegistry
from anagrafe.validators import valida_riferimento_cittadino


class _Contesto:
    def __init__(self, db_path, roles):
        self.bot_data = {
            "settings": SimpleNamespace(db_path=db_path),
            "roles": roles,
        }


def _chiedi(fornitore, db_path, roles, telegram_id=0):
    update = SimpleNamespace(effective_user=SimpleNamespace(id=telegram_id))
    return asyncio.run(fornitore(update, _Contesto(db_path, roles)))


# ----------------------------------------------------------------------
# Cittadini
# ----------------------------------------------------------------------

def test_un_pulsante_per_cittadino(conn, db_path, roles, cittadino):
    voci = _chiedi(fornitori_scelte.cittadini, db_path, roles)
    assert len(voci) == 1
    assert voci[0].chiave == f"#{cittadino}"
    assert "Mario" in voci[0].etichetta
    assert "ROSSI" in voci[0].etichetta  # il cognome in maiuscolo, come negli elenchi
    assert "@mariorossi" in voci[0].etichetta


def test_i_cittadini_sono_in_ordine_alfabetico(conn, db_path, roles):
    for telegram_id, nome in ((1, "Zeno"), (2, "Anna"), (3, "Marco")):
        repository.insert_citizen(conn, telegram_id, None, nome, "Bianchi")

    voci = _chiedi(fornitori_scelte.cittadini, db_path, roles)
    assert [v.etichetta.split()[0] for v in voci] == ["Anna", "Marco", "Zeno"]


def test_un_cittadino_senza_tag_non_mostra_parentesi_vuote(conn, db_path, roles):
    repository.insert_citizen(conn, 1, None, "Anna", "Bianchi")
    assert _chiedi(fornitori_scelte.cittadini, db_path, roles)[0].etichetta == "Anna BIANCHI"


def test_registro_vuoto(conn, db_path, roles):
    assert _chiedi(fornitori_scelte.cittadini, db_path, roles) == []


def test_la_chiave_di_un_cittadino_identifica_la_persona(conn, db_path, roles, cittadino):
    """«#12» fissa la persona anche se il tag passa a qualcun altro."""
    voce = _chiedi(fornitori_scelte.cittadini, db_path, roles)[0]
    riferimento = valida_riferimento_cittadino(voce.chiave)
    assert controlli.risolvi_cittadino(conn, riferimento)["citizen_id"] == cittadino


# ----------------------------------------------------------------------
# Amministratori
# ----------------------------------------------------------------------

def test_il_root_non_compare_fra_gli_amministratori_rimovibili(
    conn, db_path, admins_path, root_id
):
    admins_path.write_text("201\n", encoding="utf-8")
    roles = RoleRegistry(root_admin_id=root_id, admins_path=admins_path)

    voci = _chiedi(fornitori_scelte.amministratori, db_path, roles)
    assert [v.chiave for v in voci] == ["201"]


def test_un_admin_cittadino_si_riconosce_dal_nome(
    conn, db_path, admins_path, root_id
):
    repository.insert_citizen(conn, 201, "capo", "Carla", "Verdi")
    admins_path.write_text("201\n", encoding="utf-8")
    roles = RoleRegistry(root_admin_id=root_id, admins_path=admins_path)

    voce = _chiedi(fornitori_scelte.amministratori, db_path, roles)[0]
    assert "Carla VERDI" in voce.etichetta


def test_un_admin_non_cittadino_resta_un_numero(conn, db_path, admins_path, root_id):
    admins_path.write_text("201\n", encoding="utf-8")
    roles = RoleRegistry(root_admin_id=root_id, admins_path=admins_path)

    assert _chiedi(fornitori_scelte.amministratori, db_path, roles)[0].etichetta == "201"


def test_senza_altri_admin_non_ci_e_nulla_da_rimuovere(conn, db_path, roles):
    assert _chiedi(fornitori_scelte.amministratori, db_path, roles) == []


# ----------------------------------------------------------------------
# Attività
# ----------------------------------------------------------------------

def test_il_proprietario_vede_solo_le_proprie(conn, db_path, roles, cittadino, attivita):
    repository.create_attivita(conn, 777, None, "Altrui", "privata", "Non mia.")

    voci = _chiedi(fornitori_scelte.attivita_rimovibili, db_path, roles, telegram_id=12345)
    assert [v.chiave for v in voci] == [str(attivita)]
    assert voci[0].etichetta.endswith("Pizzeria Da Mario")


def test_un_admin_vede_tutte_le_attivita(
    conn, db_path, admins_path, root_id, cittadino, attivita
):
    repository.create_attivita(conn, 777, None, "Altrui", "privata", "Non mia.")
    roles = RoleRegistry(root_admin_id=root_id, admins_path=admins_path)

    voci = _chiedi(
        fornitori_scelte.attivita_rimovibili, db_path, roles, telegram_id=root_id
    )
    assert len(voci) == 2


def test_le_attivita_chiuse_non_si_possono_scegliere(
    conn, db_path, roles, cittadino, attivita
):
    repository.chiudi_attivita(conn, attivita, repository.ATTIVITA_CHIUSA, 12345, None)
    assert _chiedi(
        fornitori_scelte.attivita_rimovibili, db_path, roles, telegram_id=12345
    ) == []


def test_le_proposte_non_si_possono_rimuovere(conn, db_path, roles, cittadino):
    """Non sono nel registro: si approvano o si rifiutano, non si rimuovono."""
    repository.crea_proposta(conn, 12345, "mariorossi", "Proposta", "privata", "Nuova.")
    assert _chiedi(
        fornitori_scelte.attivita_rimovibili, db_path, roles, telegram_id=12345
    ) == []


# ----------------------------------------------------------------------
# L'invariante: una scelta a pulsante passa dal validatore del suo campo
# ----------------------------------------------------------------------

def test_ogni_scelta_passa_il_validatore_del_proprio_campo(
    conn, db_path, admins_path, root_id, cittadino, attivita
):
    """L'equivalente dinamico di test_ogni_opzione_passa_il_proprio_validatore.

    Un pulsante produce una chiave che prosegue nello stesso percorso del testo
    scritto a mano. Se un fornitore e il validatore del suo campo si
    disallineassero, premere il pulsante darebbe un errore di validazione: qui
    si verifica con dati veri che non accada.
    """
    admins_path.write_text("201\n", encoding="utf-8")
    roles = RoleRegistry(root_admin_id=root_id, admins_path=admins_path)

    provati = 0
    for comando in COMMANDS:
        for campo in comando.campi:
            if not campo.a_scelte:
                continue
            fornitore = fornitori_scelte.FORNITORI[campo.scelte]
            voci = _chiedi(fornitore, db_path, roles, telegram_id=root_id)
            assert voci, f"{comando.nome}.{campo.chiave}: nessuna voce da provare"
            for voce in voci:
                campo.validatore(voce.chiave)  # non deve sollevare
                provati += 1

    assert provati, "il test non ha provato nulla"
