#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time
import sys
import threading
import os
from typing import Dict, Any

# from flask import Flask, jsonify, render_template
from flask import Flask, jsonify, render_template

# Tasmota Steckdosen Steuerung
from tasmota_power import tasmota_get_state, tasmota_set_state

# Version
from printfleet import __version__ as PRINTFLEET_VERSION

# PrintFleet Datenbank
from printfleet.db import (
    get_db_connection,
    init_db_schema_only,
    load_settings_from_db,
    load_printers_from_db,
    get_printer_by_id,
)

# PrintFleet Sprachen und Übersetzungen
from printfleet.i18n import init_i18n, _

# Export und Backup Printers und Settings
from printfleet.export import bp as export_bp


# Blueprints
from printfleet.dashboard import bp as dashboard_bp
from printfleet.printers import bp as printers_bp
from printfleet.settings import bp as settings_bp
from printfleet.debug import bp as debug_bp
from printfleet.state import state_lock, printer_state
from printfleet.backends import fetch_moonraker, fetch_octoprint
from printfleet.info import bp as info_bp

# Monitoring
from printfleet.monitor import (
    db_watch_loop,
    create_initial_state,
    start_monitor_threads,
    join_monitor_threads,
)


# -------------------------------------------------
# Konfiguration laden (nur GLOBAL)
# -------------------------------------------------
try:
    from PrintFleetPrinterList import GLOBAL
except Exception as e:
    print("Konfigurationsdatei 'PrintFleetPrinterList.py' fehlt/fehlerhaft.", file=sys.stderr)
    raise


# -------------------------------------------------
# i18n-Verzeichnis (Übersetzungen)
# -------------------------------------------------
I18N_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "i18n")


# -------------------------------------------------
# Flask-App mit Template- und Static-Ordner
# -------------------------------------------------
app = Flask(__name__, static_folder="static", template_folder="templates")

# Blueprint(s) registrieren
app.register_blueprint(dashboard_bp)
app.register_blueprint(printers_bp)
app.register_blueprint(settings_bp)
app.register_blueprint(debug_bp)
app.register_blueprint(info_bp)
app.register_blueprint(export_bp)


def get_current_language() -> str:
    """Aktuelle Sprache aus den Settings in der DB ermitteln."""
    settings = load_settings_from_db()
    return settings.get("language") or "en"


# DB-Struktur sicherstellen
init_db_schema_only()

# i18n an die Flask-App hängen
init_i18n(app, get_current_language, I18N_DIR)


# aktive Monitor-Threads nach Drucker-ID
monitor_threads: Dict[int, threading.Thread] = {}


@app.context_processor
def inject_app_version():
    return {"app_version": PRINTFLEET_VERSION}

@app.context_processor
def inject_config():
    return {"config": app.config}


# ----------------- MAIN -----------------

if __name__ == "__main__":
    # Aktuelle Drucker einmalig aus der DB laden
    printers = load_printers_from_db()

    # Initiale Platzhalter für vorhandene Drucker im globalen Status anlegen
    create_initial_state(printers)

    # Gemeinsames Stop-Event für alle Threads
    global_stop_evt = threading.Event()

    # Monitor-Threads für vorhandene Drucker starten
    start_monitor_threads(printers, global_stop_evt)

    # DB-Watcher starten (beobachtet Settings + neue Drucker)
    watcher_thread = threading.Thread(
        target=db_watch_loop,
        args=(global_stop_evt,),
        daemon=True,
    )
    watcher_thread.start()

    print("=== Registered routes ===")
    for rule in app.url_map.iter_rules():
        print(rule.endpoint, "->", rule.rule)
    print("=========================")


    try:
        app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
    finally:
        global_stop_evt.set()
        join_monitor_threads(timeout=2.0)
        watcher_thread.join(timeout=2.0)