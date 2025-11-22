#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import Any, Dict

from flask import render_template, request

from printfleet.db import get_db_connection, load_settings_from_db
from printfleet.i18n import _
from . import bp


@bp.route("/settings", methods=["GET", "POST"])
def settings_page() -> str:
    """Globale Einstellungen (Settings-Tabelle) über ein Formular verwalten."""

    error = None
    message = None

    # Immer frische Settings aus der DB holen
    current_settings: Dict[str, Any] = load_settings_from_db()

    # Startwerte aus den aktuell geladenen Settings
    current_poll = float(current_settings.get("poll_interval", 5.0))
    current_reload = float(current_settings.get("db_reload_interval", 30.0))
    current_chat_id = current_settings.get("telegram_chat_id") or ""
    current_lang = current_settings.get("language", "en")

    # Werte, die wir ans Template geben
    form_values = {
        "poll_interval": current_poll,
        "db_reload_interval": current_reload,
        "telegram_chat_id": current_chat_id,
        "language": current_lang,
    }

    if request.method == "POST":
        poll_raw = (request.form.get("poll_interval") or "").strip()
        reload_raw = (request.form.get("db_reload_interval") or "").strip()
        chat_id = (request.form.get("telegram_chat_id") or "").strip()
        language = (request.form.get("language") or "").strip() or "en"

        # Standardmäßig: leere Chat-ID als NULL in der DB
        chat_id_db = chat_id if chat_id else None

        # Validierung
        try:
            poll = float(poll_raw) if poll_raw else current_poll
            if poll <= 0:
                raise ValueError
        except ValueError:
            error = _("settings_error_poll_interval")
            poll = current_poll  # Fallback

        try:
            reload_interval = float(reload_raw) if reload_raw else current_reload
            if reload_interval < 5:
                # Wir erlauben keine Reload-Werte kleiner 5 Sekunden
                reload_interval = 5.0
        except ValueError:
            if not error:
                error = _("settings_error_db_reload")
            reload_interval = current_reload  # Fallback

        # Werte für das Template aktualisieren (damit das Formular die Eingaben zeigt)
        form_values["poll_interval"] = poll_raw or poll
        form_values["db_reload_interval"] = reload_raw or reload_interval
        form_values["telegram_chat_id"] = chat_id
        form_values["language"] = language

        if not error:
            # In DB schreiben
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE settings
                SET poll_interval = ?, db_reload_interval = ?, telegram_chat_id = ?, language = ?
                WHERE id = 1
                """,
                (poll, reload_interval, chat_id_db, language),
            )
            conn.commit()
            conn.close()

            message = "Einstellungen gespeichert."

            # Settings für das Formular nach dem Speichern nochmal frisch laden
            saved = load_settings_from_db()
            form_values["poll_interval"] = saved.get("poll_interval", poll)
            form_values["db_reload_interval"] = saved.get("db_reload_interval", reload_interval)
            form_values["telegram_chat_id"] = saved.get("telegram_chat_id") or ""
            form_values["language"] = saved.get("language", language)

    return render_template(
        "settings.html",
        page="settings",
        settings=form_values,
        error=error,
        message=message,
    )