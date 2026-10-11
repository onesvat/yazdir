"""Minimal gettext: reads locale/<lang>.po directly, so no compile step is needed.

The language comes from YAZDIR_LANG, then the "language" key in settings.json,
then the usual LANGUAGE / LC_ALL / LC_MESSAGES / LANG.
English is the source language; missing translations fall back to it.
"""

import ast
import json
import os
from pathlib import Path

LOCALE_DIR = Path(__file__).parent / "locale"
SETTINGS_FILE = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "yazdir/settings.json"
LANGUAGES = {"en": "English", "tr": "Türkçe"}


def _language():
    if os.environ.get("YAZDIR_LANG"):
        return os.environ["YAZDIR_LANG"]
    try:
        chosen = json.loads(SETTINGS_FILE.read_text()).get("language", "system")
    except (OSError, ValueError):
        chosen = "system"
    if chosen in LANGUAGES:
        return chosen
    for var in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        value = os.environ.get(var, "")
        for part in value.split(":"):
            code = part.split(".")[0].split("_")[0].lower()
            if code and code not in ("c", "posix"):
                return code
    return "en"


def _parse_po(path: Path):
    catalog, msgid, msgstr, field = {}, None, None, None

    def flush():
        if msgid and msgstr:
            catalog[msgid] = msgstr

    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith("msgid "):
            flush()
            msgid, msgstr, field = ast.literal_eval(line[6:]), None, "id"
        elif line.startswith("msgstr "):
            msgstr, field = ast.literal_eval(line[7:]), "str"
        elif line.startswith('"') and field:
            text = ast.literal_eval(line)
            if field == "id":
                msgid += text
            else:
                msgstr += text
        elif not line or line.startswith("#"):
            field = None if not line else field
    flush()
    return catalog


LANGUAGE = _language()
_po = LOCALE_DIR / f"{LANGUAGE}.po"
_catalog = _parse_po(_po) if _po.exists() else {}


def _(message: str) -> str:
    return _catalog.get(message, message)
