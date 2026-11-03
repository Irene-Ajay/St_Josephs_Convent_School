"""Configuration.

Everything the school might need to change lives here or in settings.ini,
so nobody has to edit Python to change the attendance threshold or the
school's email address.
"""

from __future__ import annotations

import configparser
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

# The entire database is this one file. Backing up the system means copying
# it. That single property is worth more to a school with no IT staff than
# every feature in the original design.
DB_PATH = DATA_DIR / "school.db"
DATABASE_URL = f"sqlite:///{DB_PATH}"

SETTINGS_FILE = DATA_DIR / "settings.ini"

DEFAULTS = {
    "school": {
        "name": "St. Joseph's Convent School",
        "short_name": "St. Joseph's",
        "address": "",
        "phone": "",
        "email": "",
    },
    "attendance": {
        "threshold_percent": "75",
        "alert_after_consecutive_absences": "2",
    },
    "email": {
        # Gmail works with an App Password (free). Leave enabled=false until
        # the school provides one; the system runs fine without email.
        "enabled": "false",
        "smtp_host": "smtp.gmail.com",
        "smtp_port": "587",
        "username": "",
        "password": "",
        "from_name": "St. Joseph's Convent School",
    },
    "security": {
        "secret_key": "",  # generated on first run
    },
    "database": {
        # DELETE is safe everywhere, including OneDrive/Drive/network folders.
        # Only change to WAL if the data folder is on a local disk.
        "journal_mode": "DELETE",
    },
    "backup": {
        # A second copy goes here if set. Should be a pen drive, network
        # share, or the SCHOOL's own synced folder - not the same disk.
        # Example: E:\\SchoolBackups  or  C:\\Users\\Office\\Google Drive\\School
        "second_location": "",
    },
}


def _load() -> configparser.ConfigParser:
    parser = configparser.ConfigParser()
    parser.read_dict(DEFAULTS)
    if SETTINGS_FILE.exists():
        parser.read(SETTINGS_FILE, encoding="utf-8")

    if not parser.get("security", "secret_key"):
        parser.set("security", "secret_key", os.urandom(32).hex())
        _save(parser)
    return parser


def _save(parser: configparser.ConfigParser) -> None:
    with SETTINGS_FILE.open("w", encoding="utf-8") as fh:
        parser.write(fh)


settings = _load()


def get(section: str, key: str, fallback: str = "") -> str:
    return settings.get(section, key, fallback=fallback)


def get_int(section: str, key: str, fallback: int = 0) -> int:
    try:
        return int(settings.get(section, key, fallback=str(fallback)))
    except ValueError:
        return fallback


def get_bool(section: str, key: str) -> bool:
    return settings.get(section, key, fallback="false").strip().lower() in {
        "true", "yes", "1", "on",
    }


def update(section: str, key: str, value: str) -> None:
    if not settings.has_section(section):
        settings.add_section(section)
    settings.set(section, key, value)
    _save(settings)


SCHOOL_NAME = get("school", "name")
SECRET_KEY = get("security", "secret_key")
ATTENDANCE_THRESHOLD = get_int("attendance", "threshold_percent", 75)
