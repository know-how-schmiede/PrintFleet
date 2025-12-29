#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sqlite3
from typing import Any, Dict
from urllib.parse import quote

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

    def build_rtsp_url(host: str, user: str, password: str) -> str:
        if not host or not user or not password:
            return ""
        safe_user = quote(user, safe="")
        safe_password = quote(password, safe="")
        return f"rtsp://{safe_user}:{safe_password}@{host}:554/stream1"

    # Immer frische Settings aus der DB holen
    current_settings: Dict[str, Any] = load_settings_from_db()

    # Startwerte aus den aktuell geladenen Settings
    current_poll = float(current_settings.get("poll_interval", 5.0))
    current_reload = float(current_settings.get("db_reload_interval", 30.0))
    current_chat_id = current_settings.get("telegram_chat_id") or ""
    current_lang = current_settings.get("language", "en")
    current_imprint_md = current_settings.get("imprint_markdown") or ""
    current_privacy_md = current_settings.get("privacy_markdown") or ""
    current_kiosk_stream = current_settings.get("kiosk_stream_url") or ""
    current_kiosk_host = current_settings.get("kiosk_camera_host") or ""
    current_kiosk_user = current_settings.get("kiosk_camera_user") or ""
    current_kiosk_password = current_settings.get("kiosk_camera_password") or ""
    current_kiosk_layout = current_settings.get("kiosk_stream_layout") or "standard"

    # Werte, die wir ans Template geben
    form_values = {
        "poll_interval": current_poll,
        "db_reload_interval": current_reload,
        "telegram_chat_id": current_chat_id,
        "language": current_lang,
        "imprint_markdown": current_imprint_md,
        "privacy_markdown": current_privacy_md,
        "kiosk_stream_url": current_kiosk_stream,
        "kiosk_camera_host": current_kiosk_host,
        "kiosk_camera_user": current_kiosk_user,
        "kiosk_camera_password": current_kiosk_password,
        "kiosk_stream_layout": current_kiosk_layout,
    }

    for idx in range(1, 5):
        stream_url = current_settings.get(f"kiosk_stream_url_{idx}") or ""
        cam_host = current_settings.get(f"kiosk_camera_host_{idx}") or ""
        cam_user = current_settings.get(f"kiosk_camera_user_{idx}") or ""
        cam_password = current_settings.get(f"kiosk_camera_password_{idx}") or ""
        generated = build_rtsp_url(cam_host, cam_user, cam_password)
        form_values[f"kiosk_stream_url_{idx}"] = stream_url
        form_values[f"kiosk_camera_host_{idx}"] = cam_host
        form_values[f"kiosk_camera_user_{idx}"] = cam_user
        form_values[f"kiosk_camera_password_{idx}"] = cam_password
        form_values[f"kiosk_stream_generated_{idx}"] = generated

    if request.method == "POST":
        poll_raw = (request.form.get("poll_interval") or "").strip()
        reload_raw = (request.form.get("db_reload_interval") or "").strip()
        chat_id = (request.form.get("telegram_chat_id") or "").strip()
        language = (request.form.get("language") or "").strip() or "en"
        imprint_markdown = request.form.get("imprint_markdown") or ""
        privacy_markdown = request.form.get("privacy_markdown") or ""
        kiosk_stream_url = (request.form.get("kiosk_stream_url") or "").strip()
        kiosk_camera_host = (request.form.get("kiosk_camera_host") or "").strip()
        kiosk_camera_user = (request.form.get("kiosk_camera_user") or "").strip()
        kiosk_camera_password = request.form.get("kiosk_camera_password") or ""
        kiosk_stream_layout = (request.form.get("kiosk_stream_layout") or "").strip() or "standard"

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
        form_values["imprint_markdown"] = imprint_markdown
        form_values["privacy_markdown"] = privacy_markdown
        form_values["kiosk_stream_url"] = kiosk_stream_url
        form_values["kiosk_camera_host"] = kiosk_camera_host
        form_values["kiosk_camera_user"] = kiosk_camera_user
        form_values["kiosk_camera_password"] = kiosk_camera_password
        form_values["kiosk_stream_layout"] = kiosk_stream_layout

        stream_values: Dict[str, str] = {}
        for idx in range(1, 5):
            stream_values[f"kiosk_stream_url_{idx}"] = (request.form.get(f"kiosk_stream_url_{idx}") or "").strip()
            stream_values[f"kiosk_camera_host_{idx}"] = (request.form.get(f"kiosk_camera_host_{idx}") or "").strip()
            stream_values[f"kiosk_camera_user_{idx}"] = (request.form.get(f"kiosk_camera_user_{idx}") or "").strip()
            stream_values[f"kiosk_camera_password_{idx}"] = request.form.get(f"kiosk_camera_password_{idx}") or ""

            form_values[f"kiosk_stream_url_{idx}"] = stream_values[f"kiosk_stream_url_{idx}"]
            form_values[f"kiosk_camera_host_{idx}"] = stream_values[f"kiosk_camera_host_{idx}"]
            form_values[f"kiosk_camera_user_{idx}"] = stream_values[f"kiosk_camera_user_{idx}"]
            form_values[f"kiosk_camera_password_{idx}"] = stream_values[f"kiosk_camera_password_{idx}"]
            form_values[f"kiosk_stream_generated_{idx}"] = build_rtsp_url(
                stream_values[f"kiosk_camera_host_{idx}"],
                stream_values[f"kiosk_camera_user_{idx}"],
                stream_values[f"kiosk_camera_password_{idx}"],
            )

        if not error:
            # In DB schreiben
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE settings
                SET poll_interval = ?,
                    db_reload_interval = ?,
                    telegram_chat_id = ?,
                    language = ?,
                    imprint_markdown = ?,
                    privacy_markdown = ?,
                    kiosk_stream_url = ?,
                    kiosk_camera_host = ?,
                    kiosk_camera_user = ?,
                    kiosk_camera_password = ?,
                    kiosk_stream_layout = ?,
                    kiosk_stream_url_1 = ?,
                    kiosk_camera_host_1 = ?,
                    kiosk_camera_user_1 = ?,
                    kiosk_camera_password_1 = ?,
                    kiosk_stream_url_2 = ?,
                    kiosk_camera_host_2 = ?,
                    kiosk_camera_user_2 = ?,
                    kiosk_camera_password_2 = ?,
                    kiosk_stream_url_3 = ?,
                    kiosk_camera_host_3 = ?,
                    kiosk_camera_user_3 = ?,
                    kiosk_camera_password_3 = ?,
                    kiosk_stream_url_4 = ?,
                    kiosk_camera_host_4 = ?,
                    kiosk_camera_user_4 = ?,
                    kiosk_camera_password_4 = ?
                WHERE id = 1
                """,
                (
                    poll,
                    reload_interval,
                    chat_id_db,
                    language,
                    imprint_markdown,
                    privacy_markdown,
                    kiosk_stream_url,
                    kiosk_camera_host,
                    kiosk_camera_user,
                    kiosk_camera_password,
                    kiosk_stream_layout,
                    stream_values["kiosk_stream_url_1"],
                    stream_values["kiosk_camera_host_1"],
                    stream_values["kiosk_camera_user_1"],
                    stream_values["kiosk_camera_password_1"],
                    stream_values["kiosk_stream_url_2"],
                    stream_values["kiosk_camera_host_2"],
                    stream_values["kiosk_camera_user_2"],
                    stream_values["kiosk_camera_password_2"],
                    stream_values["kiosk_stream_url_3"],
                    stream_values["kiosk_camera_host_3"],
                    stream_values["kiosk_camera_user_3"],
                    stream_values["kiosk_camera_password_3"],
                    stream_values["kiosk_stream_url_4"],
                    stream_values["kiosk_camera_host_4"],
                    stream_values["kiosk_camera_user_4"],
                    stream_values["kiosk_camera_password_4"],
                ),
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
            form_values["imprint_markdown"] = saved.get("imprint_markdown") or ""
            form_values["privacy_markdown"] = saved.get("privacy_markdown") or ""
            form_values["kiosk_stream_url"] = saved.get("kiosk_stream_url") or ""
            form_values["kiosk_camera_host"] = saved.get("kiosk_camera_host") or ""
            form_values["kiosk_camera_user"] = saved.get("kiosk_camera_user") or ""
            form_values["kiosk_camera_password"] = saved.get("kiosk_camera_password") or ""
            form_values["kiosk_stream_layout"] = saved.get("kiosk_stream_layout") or "standard"

            for idx in range(1, 5):
                form_values[f"kiosk_stream_url_{idx}"] = saved.get(f"kiosk_stream_url_{idx}") or ""
                form_values[f"kiosk_camera_host_{idx}"] = saved.get(f"kiosk_camera_host_{idx}") or ""
                form_values[f"kiosk_camera_user_{idx}"] = saved.get(f"kiosk_camera_user_{idx}") or ""
                form_values[f"kiosk_camera_password_{idx}"] = saved.get(f"kiosk_camera_password_{idx}") or ""
                form_values[f"kiosk_stream_generated_{idx}"] = build_rtsp_url(
                    form_values[f"kiosk_camera_host_{idx}"],
                    form_values[f"kiosk_camera_user_{idx}"],
                    form_values[f"kiosk_camera_password_{idx}"],
                )

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
