#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import json
from typing import Dict, Any

from flask import g


def load_translations(lang_code: str, i18n_dir: str) -> dict:
    """Lädt Übersetzungen aus JSON-Dateien mit Fallback auf Englisch."""
    translations: Dict[str, Any] = {}

    # 1) Basis: Englisch immer laden
    en_path = os.path.join(i18n_dir, "en.json")
    if os.path.exists(en_path):
        try:
            with open(en_path, "r", encoding="utf-8") as f:
                translations = json.load(f)
        except Exception as e:
            print(f"[i18n] Fehler beim Laden von en.json: {e}", file=sys.stderr)

    # 2) Gewünschte Sprache darüberlegen (falls nicht englisch)
    if lang_code != "en":
        lang_path = os.path.join(i18n_dir, f"{lang_code}.json")
        if os.path.exists(lang_path):
            try:
                with open(lang_path, "r", encoding="utf-8") as f:
                    specific = json.load(f)
                translations.update(specific)
            except Exception as e:
                print(f"[i18n] Fehler beim Laden von {lang_code}.json: {e}", file=sys.stderr)

    return translations


def _(key: str) -> str:
    """Übersetzungsfunktion für Jinja-Templates."""
    if not hasattr(g, "translations"):
        return key
    return g.translations.get(key, key)


def init_i18n(app, get_language_callable, i18n_dir: str) -> None:
    """Hängt i18n an eine bestehende Flask-App.

    - get_language_callable: Funktion, die z.B. SETTINGS["language"] zurückgibt
    - i18n_dir: Pfad zum Ordner mit den JSON-Dateien
    """

    @app.before_request
    def set_language():
        """Vor jedem Request Sprache setzen und Übersetzungen laden."""
        lang = get_language_callable()
        g.lang = lang
        g.translations = load_translations(lang, i18n_dir)

    @app.context_processor
    def inject_translation_helpers():
        """Stellt _() und current_language() in allen Templates zur Verfügung."""
        return {
            "_": _,
            "current_language": lambda: getattr(g, "lang", "en"),
        }