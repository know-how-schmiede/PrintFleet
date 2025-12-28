#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import Optional, Dict, Any
import json
import os
import subprocess
import sys

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

LAN_SCAN_TIMEOUT = 120


def _normalize_host(raw: str) -> str:
    """
    Bereinigt die Host-Eingabe:
    - entfernt führendes http://, https://, http//, https//
    - trennt nach erstem / (Pfadangaben)
    - trimmt Leerzeichen
    """
    if not raw:
        return ""

    h = raw.strip()

    prefixes = ("http://", "https://", "http//", "https//")
    hl = h.lower()
    for p in prefixes:
        if hl.startswith(p):
            h = h[len(p):]
            break

    if "/" in h:
        h = h.split("/", 1)[0]

    return h.strip()


def _resolve_lan_scan_path() -> str:
    env_path = os.environ.get("PRINTFLEET_LAN_SCAN_PATH")
    if env_path:
        return env_path
    return os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            "..",
            "..",
            "lan_scan.py",
        )
    )


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

        # Host zuerst roh holen, dann normalisieren
        host_raw = (request.form.get("host") or "").strip()
        host = _normalize_host(host_raw)

        # Port-String wie vorher
        port_raw = (request.form.get("port") or "").strip()

        https_flag = 1 if request.form.get("https") == "on" else 0
        no_scanning_flag = 1 if request.form.get("no_scanning") == "on" else 0
        token = (request.form.get("token") or "").strip() or None
        api_key = (request.form.get("api_key") or "").strip() or None
        err_int_raw = (request.form.get("error_report_interval") or "").strip()

        # Tasmota-IP-Adresse
        tasmota_host = (request.form.get("tasmota_host") or "").strip() or None
        # NEU: Tasmota-Topic
        tasmota_topic = (request.form.get("tasmota_topic") or "").strip() or None

        # NEU: Standort, Druckertyp, Notizen
        location = (request.form.get("location") or "").strip() or None
        printer_type = (request.form.get("printer_type") or "").strip() or None
        notes = (request.form.get("notes") or "").strip() or None

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
                    (name,
                     backend,
                     host,
                     port,
                     https,
                     no_scanning,
                     token,
                     api_key,
                     error_report_interval,
                     tasmota_host,
                     tasmota_topic,
                     location,
                     printer_type,
                     notes,
                     enabled)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                """,
                (
                    name,
                    backend,
                    host,   # hier die bereinigte Variante verwenden
                    port,
                    https_flag,
                    no_scanning_flag,
                    token,
                    api_key,
                    error_report_interval,
                    tasmota_host,
                    tasmota_topic,
                    location,
                    printer_type,
                    notes,
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

        # Host normalisieren
        host_raw = (request.form.get("host") or "").strip()
        host = _normalize_host(host_raw)

        port_raw = (request.form.get("port") or "").strip()
        https_flag = 1 if request.form.get("https") == "on" else 0
        no_scanning_flag = 1 if request.form.get("no_scanning") == "on" else 0
        token = (request.form.get("token") or "").strip() or None
        api_key = (request.form.get("api_key") or "").strip() or None
        err_int_raw = (request.form.get("error_report_interval") or "").strip()
        enabled_flag = 1 if request.form.get("enabled") == "on" else 0

        # Tasmota-IP-Adresse
        tasmota_host = (request.form.get("tasmota_host") or "").strip() or None
        # NEU: Tasmota-Topic
        tasmota_topic = (request.form.get("tasmota_topic") or "").strip() or None

        # NEU: Standort, Druckertyp, Notizen
        location = (request.form.get("location") or "").strip() or None
        printer_type = (request.form.get("printer_type") or "").strip() or None
        notes = (request.form.get("notes") or "").strip() or None

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
                SET name = ?,
                    backend = ?,
                    host = ?,
                    port = ?,
                    https = ?,
                    no_scanning = ?,
                    token = ?,
                    api_key = ?,
                    error_report_interval = ?,
                    tasmota_host = ?,
                    tasmota_topic = ?,
                    location = ?,
                    printer_type = ?,
                    notes = ?,
                    enabled = ?
                WHERE id = ?
                """,
                (
                    name,
                    backend,
                    host,  # wieder die bereinigte Variante
                    port,
                    https_flag,
                    no_scanning_flag,
                    token,
                    api_key,
                    error_report_interval,
                    tasmota_host,
                    tasmota_topic,
                    location,
                    printer_type,
                    notes,
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


@bp.route("/api/printers/scan", methods=["POST"])
def api_printer_scan():
    scan_path = _resolve_lan_scan_path()
    if not os.path.isfile(scan_path):
        return (
            jsonify(
                {
                    "status": "error",
                    "msg": "Lan scan script not found.",
                    "details": scan_path,
                }
            ),
            500,
        )

    payload = request.get_json(silent=True) or {}
    hosts = payload.get("hosts")
    cidr = payload.get("cidr")

    cmd = [sys.executable, scan_path, "--json", "--no-progress"]
    if isinstance(hosts, list):
        host_arg = ",".join(str(h).strip() for h in hosts if str(h).strip())
        if host_arg:
            cmd += ["--hosts", host_arg]
    elif isinstance(hosts, str) and hosts.strip():
        cmd += ["--hosts", hosts.strip()]

    if isinstance(cidr, str) and cidr.strip():
        cmd += ["--cidr", cidr.strip()]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=LAN_SCAN_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return jsonify({"status": "error", "msg": "Scan timed out."}), 504

    if result.returncode != 0:
        details = (result.stderr or result.stdout or "").strip()
        return (
            jsonify({"status": "error", "msg": "Scan failed.", "details": details}),
            500,
        )

    try:
        data = json.loads(result.stdout) if result.stdout else {}
    except json.JSONDecodeError:
        return (
            jsonify(
                {
                    "status": "error",
                    "msg": "Invalid scan output.",
                    "details": (result.stdout or "").strip(),
                }
            ),
            500,
        )

    return jsonify(
        {
            "status": "ok",
            "results": data.get("results", []),
            "networks": data.get("networks", []),
            "hosts": data.get("hosts", []),
        }
    )


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
