"""Configurazione letta dall'ambiente (e da un eventuale file .env)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from dotenv import load_dotenv

# Radice del progetto: la cartella che contiene il pacchetto anagrafe/
BASE_DIR = Path(__file__).resolve().parent.parent


class ConfigurazioneMancante(RuntimeError):
    """Manca (o non è valida) una variabile d'ambiente obbligatoria."""


@dataclass(frozen=True)
class Settings:
    """Tutti i parametri di avvio del bot, in un unico oggetto immutabile."""

    token: str
    root_admin_id: int
    log_channel_id: int | str | None
    db_path: Path
    admins_path: Path


def _canale_log(valore: str | None) -> int | str | None:
    """Il canale di log può essere un ID numerico (-1001234567890) o un @username."""
    if not valore:
        return None
    valore = valore.strip()
    if not valore:
        return None
    try:
        return int(valore)
    except ValueError:
        return valore


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    """Costruisce le Settings leggendo l'ambiente.

    Se `env` non è passato carica il file .env dalla radice del progetto e usa
    os.environ. Passare un dizionario esplicito serve ai test.
    """
    if env is None:
        load_dotenv(BASE_DIR / ".env")
        env = os.environ

    token = (env.get("TOKEN_CITIZENS_BOT") or "").strip()
    if not token:
        raise ConfigurazioneMancante(
            "Manca la variabile d'ambiente TOKEN_CITIZENS_BOT: inserisci il token "
            "ottenuto da BotFather nel file .env (vedi .env.example)."
        )

    root_grezzo = (env.get("ROOT_ADMIN_ID") or "").strip()
    if not root_grezzo:
        raise ConfigurazioneMancante(
            "Manca la variabile d'ambiente ROOT_ADMIN_ID: inserisci l'ID Telegram "
            "dell'utente root nel file .env (vedi .env.example)."
        )
    try:
        root_admin_id = int(root_grezzo)
    except ValueError as exc:
        raise ConfigurazioneMancante(
            f"ROOT_ADMIN_ID deve essere un numero intero, trovato {root_grezzo!r}."
        ) from exc

    db_path = Path(env.get("ANAGRAFE_DB_PATH") or (BASE_DIR / "registro.db"))
    admins_path = Path(env.get("ANAGRAFE_ADMINS_PATH") or (BASE_DIR / "admins.txt"))

    return Settings(
        token=token,
        root_admin_id=root_admin_id,
        log_channel_id=_canale_log(env.get("LOG_CHANNEL_ID")),
        db_path=db_path,
        admins_path=admins_path,
    )
