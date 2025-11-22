#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import Optional, Dict, Any

from flask import (
    render_template,
    request,
    redirect,
    url_for,
    abort,
    jsonify,
)

from tasmota_power import tasmota_get_state, tasmota_set_state

from printfleet.db import get_db_connection, get_printer_by_id
from printfleet.i18n import _
from . import bp


@bp.route("/printers")
def printer_list() -> str:
    """Liste aller Drucker anzeigen."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM printers ORDER BY id")
    printers = cur.fetchall()
    conn.close()
    return render_template("printers_list.html", page="printers", printers=printers)


@bp.route("/printers/new", methods=["GET", "POST"])
def printer_new() -> str:
    """Neuen Drucker anlegen."""
    error = None

    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        backend = (request.form.get("backend") or "").strip()
        host = (request.form.get("host") or "").strip()
        port_raw = (request.form.get("port") or "").strip()
        https_flag = 1 if request.form.get("https") == "on" else 0
        token = (request.form.get("token") or "").strip() or None
        api_key = (request.form.get("api_key") or "").strip() or None
        err_int_raw = (request.form.get("error_report_interval") or "").strip()
        # Tasmota-IP-Adresse
        tasmota_host = (request.form.get("tasmota_host") or "").strip() or None

        # Simple Pflichtfelder-Prüfung
        if not name or not backend or not host or not port_raw:
            error = _("printer_error_required_fields")
        else:
            try:
                port = int(port_raw)
            except ValueError:
                error = _("printer_error_port_number")

        if not error:
            try:
                error_report_interval = float(err_int_raw) if err_int_raw else 30.0
            except ValueError:
                error_report_interval = 30.0

            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO printers
                    (name, backend, host, port, https, token, api_key,
                     error_report_interval, tasmota_host, enabled)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                """,
                (
                    name,
                    backend,
                    host,
                    port,
                    https_flag,
                    token,
                    api_key,
                    error_report_interval,
                    tasmota_host,
                ),
            )
            conn.commit()
            new_id = cur.lastrowid
            conn.close()
            # Nach dem Anlegen direkt zur Detailseite
            return redirect(url_for("printers.printer_edit", printer_id=new_id))

    # GET oder Fehlerfall
    return render_template(
        "printer_form.html",
        page="printers",
        printer=None,
        error=error,
        mode="new",
    )


@bp.route("/printers/<int:printer_id>", methods=["GET", "POST"])
def printer_edit(printer_id: int) -> str:
    """Bestehenden Drucker bearbeiten."""
    printer = get_printer_by_id(printer_id)
    if printer is None:
        abort(404)

    error = None

    if request.method == "POST":
        # Update-Formular
        name = (request.form.get("name") or "").strip()
        backend = (request.form.get("backend") or "").strip()
        host = (request.form.get("host") or "").strip()
        port_raw = (request.form.get("port") or "").strip()
        https_flag = 1 if request.form.get("https") == "on" else 0
        token = (request.form.get("token") or "").strip() or None
        api_key = (request.form.get("api_key") or "").strip() or None
        err_int_raw = (request.form.get("error_report_interval") or "").strip()
        enabled_flag = 1 if request.form.get("enabled") == "on" else 0
        # Tasmota-IP-Adresse
        tasmota_host = (request.form.get("tasmota_host") or "").strip() or None

        if not name or not backend or not host or not port_raw:
            error = _("printer_error_required_fields")
        else:
            try:
                port = int(port_raw)
            except ValueError:
                error = _("printer_error_port_number")

        if not error:
            try:
                error_report_interval = float(err_int_raw) if err_int_raw else 30.0
            except ValueError:
                error_report_interval = 30.0

            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE printers
                SET name = ?, backend = ?, host = ?, port = ?, https = ?,
                    token = ?, api_key = ?, error_report_interval = ?,
                    tasmota_host = ?, enabled = ?
                WHERE id = ?
                """,
                (
                    name,
                    backend,
                    host,
                    port,
                    https_flag,
                    token,
                    api_key,
                    error_report_interval,
                    tasmota_host,
                    enabled_flag,
                    printer_id,
                ),
            )
            conn.commit()
            conn.close()
            # Neu laden, damit die Ansicht aktualisiert ist
            printer = get_printer_by_id(printer_id)

    return render_template(
        "printer_form.html",
        page="printers",
        printer=printer,
        error=error,
        mode="edit",
    )


@bp.route("/printers/<int:printer_id>/delete", methods=["POST"])
def printer_delete(printer_id: int):
    """Drucker endgültig löschen."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM printers WHERE id = ?", (printer_id,))
    conn.commit()
    conn.close()
    # Liste neu anzeigen
    return redirect(url_for("printers.printer_list"))


@bp.route("/api/printer/<int:printer_id>/power/status")
def api_printer_power_status(printer_id):
    printer = get_printer_by_id(printer_id)
    if printer is None:
        return jsonify({"status": "error", "msg": "Printer not found"}), 404

    ip = printer["tasmota_host"]
    if not ip:
        return jsonify({"status": "error", "msg": "No Tasmota IP configured"}), 400

    state = tasmota_get_state(ip)  # 'ON', 'OFF', 'UNKNOWN'
    return jsonify({"status": "ok", "state": state})


@bp.route("/api/printer/<int:printer_id>/power/toggle", methods=["POST"])
def api_printer_power_toggle(printer_id):
    printer = get_printer_by_id(printer_id)
    if printer is None:
        return jsonify({"status": "error", "msg": "Printer not found"}), 404

    ip = printer["tasmota_host"]
    if not ip:
        return jsonify({"status": "error", "msg": "No Tasmota IP configured"}), 400

    current = tasmota_get_state(ip)  # 'ON' / 'OFF' / 'UNKNOWN'

    if current == "ON":
        target_on = False
        target_state = "OFF"
    elif current == "OFF":
        target_on = True
        target_state = "ON"
    else:
        # UNKNOWN → wir versuchen einzuschalten
        target_on = True
        target_state = "ON"

    ok = tasmota_set_state(ip, target_on)
    new_state = tasmota_get_state(ip) if ok else current

    return jsonify(
        {
            "status": "ok" if ok else "error",
            "requested": target_state,
            "state": new_state,
        }
    ), (200 if ok else 500)