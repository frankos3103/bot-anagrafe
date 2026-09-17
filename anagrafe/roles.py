"""Ruoli e gestione degli amministratori (file admins.txt)."""

from __future__ import annotations

import logging
from enum import IntEnum
from pathlib import Path

logger = logging.getLogger(__name__)


class Role(IntEnum):
    """I tre livelli di autorizzazione, ordinati per potere crescente."""

    PUBBLICO = 0
    ADMIN = 1
    ROOT = 2


ETICHETTE_RUOLO = {
    Role.PUBBLICO: "cittadino",
    Role.ADMIN: "amministratore",
    Role.ROOT: "root",
}


class RoleRegistry:
    """Decide chi può fare cosa, leggendo l'elenco admin da un file di testo.

    Il file contiene un ID Telegram per riga; righe vuote e righe che iniziano
    con # sono ignorate. Viene riletto a ogni interrogazione, così modificarlo
    a mano non richiede di riavviare il bot.
    """

    def __init__(self, root_admin_id: int, admins_path: Path | str) -> None:
        self.root_admin_id = root_admin_id
        self.admins_path = Path(admins_path)

    # ------------------------------------------------------------------
    # Lettura
    # ------------------------------------------------------------------

    def admin_ids(self) -> set[int]:
        """Gli ID presenti in admins.txt (il root non è incluso qui)."""
        if not self.admins_path.exists():
            logger.warning("File admins.txt non trovato in %s", self.admins_path)
            return set()

        ids: set[int] = set()
        for riga in self.admins_path.read_text(encoding="utf-8").splitlines():
            riga = riga.strip()
            if not riga or riga.startswith("#"):
                continue
            try:
                ids.add(int(riga))
            except ValueError:
                logger.warning("Riga non valida in admins.txt: %r", riga)
        return ids

    def tutti_gli_admin(self) -> list[int]:
        """Tutti gli amministratori, root compreso, ordinati."""
        return sorted(self.admin_ids() | {self.root_admin_id})

    def is_root(self, user_id: int) -> bool:
        return user_id == self.root_admin_id

    def is_admin(self, user_id: int) -> bool:
        # Il root è sempre admin, anche se non compare in admins.txt.
        return self.is_root(user_id) or user_id in self.admin_ids()

    def role_of(self, user_id: int) -> Role:
        if self.is_root(user_id):
            return Role.ROOT
        if user_id in self.admin_ids():
            return Role.ADMIN
        return Role.PUBBLICO

    # ------------------------------------------------------------------
    # Scrittura
    # ------------------------------------------------------------------

    def aggiungi(self, admin_id: int) -> bool:
        """Aggiunge un ID ad admins.txt. False se era già presente."""
        if admin_id in self.admin_ids():
            return False

        testo = ""
        if self.admins_path.exists():
            testo = self.admins_path.read_text(encoding="utf-8")
        if testo and not testo.endswith("\n"):
            testo += "\n"
        testo += f"{admin_id}\n"

        self.admins_path.parent.mkdir(parents=True, exist_ok=True)
        self.admins_path.write_text(testo, encoding="utf-8")
        return True

    def rimuovi(self, admin_id: int) -> bool:
        """Rimuove un ID da admins.txt. False se non c'era. Il root non si rimuove.

        I commenti e le righe non numeriche presenti nel file vengono conservati.
        """
        if self.is_root(admin_id) or not self.admins_path.exists():
            return False

        righe = self.admins_path.read_text(encoding="utf-8").splitlines()
        trovato = False
        rimaste: list[str] = []

        for riga in righe:
            pulita = riga.strip()
            if pulita and not pulita.startswith("#"):
                try:
                    if int(pulita) == admin_id:
                        trovato = True
                        continue
                except ValueError:
                    pass
            rimaste.append(riga)

        if trovato:
            contenuto = "\n".join(rimaste).rstrip("\n")
            if contenuto:
                contenuto += "\n"
            self.admins_path.write_text(contenuto, encoding="utf-8")

        return trovato
