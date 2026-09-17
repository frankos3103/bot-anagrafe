"""Ruoli e gestione del file admins.txt."""

from anagrafe.roles import Role


def test_root_e_sempre_admin_anche_senza_file(roles, root_id):
    assert roles.is_root(root_id)
    assert roles.is_admin(root_id)
    assert roles.role_of(root_id) is Role.ROOT


def test_sconosciuto_e_pubblico(roles):
    assert not roles.is_admin(999)
    assert roles.role_of(999) is Role.PUBBLICO


def test_aggiungi_e_rimuovi(roles):
    assert roles.aggiungi(222) is True
    assert roles.is_admin(222)
    assert roles.role_of(222) is Role.ADMIN

    assert roles.rimuovi(222) is True
    assert not roles.is_admin(222)


def test_aggiungere_due_volte_non_duplica(roles, admins_path):
    assert roles.aggiungi(222) is True
    assert roles.aggiungi(222) is False
    assert admins_path.read_text(encoding="utf-8").count("222") == 1


def test_rimuovere_id_assente(roles):
    assert roles.rimuovi(333) is False


def test_il_root_non_si_rimuove(roles, root_id):
    roles.aggiungi(root_id)
    assert roles.rimuovi(root_id) is False
    assert roles.is_admin(root_id)


def test_commenti_e_righe_vuote_ignorate(roles, admins_path):
    admins_path.write_text("# amministratori\n\n222\n  333  \n", encoding="utf-8")
    assert roles.admin_ids() == {222, 333}


def test_righe_malformate_non_bloccano(roles, admins_path):
    admins_path.write_text("222\nnon-un-numero\n333\n", encoding="utf-8")
    assert roles.admin_ids() == {222, 333}


def test_rimozione_conserva_commenti(roles, admins_path):
    admins_path.write_text("# capi\n222\n333\n", encoding="utf-8")
    assert roles.rimuovi(222) is True
    contenuto = admins_path.read_text(encoding="utf-8")
    assert "# capi" in contenuto
    assert "333" in contenuto
    assert "222" not in contenuto


def test_file_senza_newline_finale(roles, admins_path):
    admins_path.write_text("222", encoding="utf-8")
    assert roles.aggiungi(333) is True
    assert roles.admin_ids() == {222, 333}


def test_tutti_gli_admin_include_il_root(roles, root_id):
    roles.aggiungi(222)
    assert roles.tutti_gli_admin() == [root_id, 222]


def test_modifica_a_caldo_del_file(roles, admins_path):
    """Il file viene riletto a ogni controllo: niente riavvio del bot."""
    assert not roles.is_admin(222)
    admins_path.write_text("222\n", encoding="utf-8")
    assert roles.is_admin(222)
