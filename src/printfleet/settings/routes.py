#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sqlite3
from typing import Any, Dict

from flask import flash, g, redirect, render_template, request, url_for
from werkzeug.security import generate_password_hash

from printfleet.db import (
    count_users,
    create_user,
    delete_user,
    get_db_connection,
    get_user_by_id,
    list_users,
    load_settings_from_db,
    update_user_password,
)
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

    users = list_users()
    current_user_id = g.user["id"] if getattr(g, "user", None) else None

    return render_template(
        "settings.html",
        page="settings",
        settings=form_values,
        error=error,
        message=message,
        users=users,
        current_user_id=current_user_id,
        user_count=len(users),
    )


@bp.route("/settings/users/create", methods=["POST"])
def create_user_from_settings() -> str:
    username = (request.form.get("username") or "").strip()
    password = request.form.get("password") or ""
    confirm = request.form.get("password_confirm") or ""

    if not username or not password:
        flash(_("users_error_required"), "danger")
        return redirect(url_for("settings.settings_page") + "#tab-users")

    if password != confirm:
        flash(_("users_error_password_mismatch"), "danger")
        return redirect(url_for("settings.settings_page") + "#tab-users")

    try:
        create_user(username, generate_password_hash(password))
    except sqlite3.IntegrityError:
        flash(_("users_error_username_exists"), "danger")
        return redirect(url_for("settings.settings_page") + "#tab-users")

    flash(_("users_user_created"), "success")
    return redirect(url_for("settings.settings_page") + "#tab-users")


@bp.route("/settings/users/<int:user_id>/password", methods=["POST"])
def reset_user_password(user_id: int) -> str:
    user = get_user_by_id(user_id)
    if not user:
        flash(_("users_error_not_found"), "danger")
        return redirect(url_for("settings.settings_page") + "#tab-users")

    new_password = request.form.get("new_password") or ""
    confirm = request.form.get("confirm_password") or ""

    if not new_password or not confirm:
        flash(_("users_error_password_required"), "danger")
        return redirect(url_for("settings.settings_page") + "#tab-users")

    if new_password != confirm:
        flash(_("users_error_password_mismatch"), "danger")
        return redirect(url_for("settings.settings_page") + "#tab-users")

    update_user_password(user_id, generate_password_hash(new_password))
    flash(_("users_password_updated"), "success")
    return redirect(url_for("settings.settings_page") + "#tab-users")


@bp.route("/settings/users/<int:user_id>/delete", methods=["POST"])
def delete_user_from_settings(user_id: int) -> str:
    if getattr(g, "user", None) and g.user["id"] == user_id:
        flash(_("users_error_delete_self"), "danger")
        return redirect(url_for("settings.settings_page") + "#tab-users")

    if count_users() <= 1:
        flash(_("users_error_last_user"), "danger")
        return redirect(url_for("settings.settings_page") + "#tab-users")

    user = get_user_by_id(user_id)
    if not user:
        flash(_("users_error_not_found"), "danger")
        return redirect(url_for("settings.settings_page") + "#tab-users")

    delete_user(user_id)
    flash(_("users_user_deleted"), "success")
    return redirect(url_for("settings.settings_page") + "#tab-users")
