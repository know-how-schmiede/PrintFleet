#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time
import sys
import threading
import requests
import sqlite3
import os
import json
from typing import Optional, Dict, Any

# from flask import Flask, jsonify, render_template
from flask import Flask, jsonify, render_template, g, request, redirect, url_for, abort

# Tasmota Steckdosen Steuerung
from tasmota_power import tasmota_get_state, tasmota_set_state


# -------------------------------------------------
# Konfiguration laden (nur GLOBAL)
# -------------------------------------------------
try:
    from PrintFleetPrinterList import GLOBAL
except Exception as e:
    print("Konfigurationsdatei 'PrintFleetPrinterList.py' fehlt/fehlerhaft.", file=sys.stderr)
    raise


# -------------------------------------------------
# SQLite: Struktur anlegen (printers + settings)
# -------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "PrintFleet.sqlite3")
I18N_DIR = os.path.join(BASE_DIR, "i18n")

# -------------------------------------------------
# Flask-App mit Template- und Static-Ordner
# -------------------------------------------------
app = Flask(__name__, static_folder="static", template_folder="templates")

state_lock = threading.Lock()
printer_state: Dict[str, Dict[str, Any]] = {}

def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db_schema_only() -> None:
    """Erzeugt (falls nötig) die Tabellen `printers` und `settings`.

    - `printers` enthält nur noch druckerspezifische Daten
    - `settings` enthält globale Einstellungen wie Poll-Intervall,
      DB-Reload-Intervall und eine globale Telegram-Chat-ID

    Die eigentlichen Drucker-Datensätze werden extern (z.B. mit einem
    DB-Tool) gepflegt und später über ein Web-Formular ergänzt.
    """
    conn = get_db_connection()
    cur = conn.cursor()

    # Druckertabelle – jetzt mit NOT NULL + DEFAULT für error_report_interval
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS printers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            backend TEXT NOT NULL,
            host TEXT NOT NULL,
            port INTEGER NOT NULL,
            https INTEGER NOT NULL DEFAULT 0,
            token TEXT,
            api_key TEXT,
            error_report_interval REAL NOT NULL DEFAULT 30.0,
            -- Platzhalter für spätere Erweiterungen
            tasmota_host TEXT,
            tasmota_topic TEXT,
            location TEXT,
            printer_type TEXT,
            notes TEXT,
            enabled INTEGER NOT NULL DEFAULT 1
        );
        """
    )

    # Globale Settings-Tabelle
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            poll_interval REAL,
            db_reload_interval REAL,
            telegram_chat_id TEXT,
            language TEXT
        );
        """
    )

    # Migration für bestehende Installationen:
    cur.execute("PRAGMA table_info(settings)")
    cols = [r[1] for r in cur.fetchall()]
    if "language" not in cols:
        cur.execute("ALTER TABLE settings ADD COLUMN language TEXT")


    # Falls noch kein Settings-Datensatz existiert, einen Default-Eintrag erzeugen
    cur.execute("SELECT COUNT(*) AS cnt FROM settings")
    row = cur.fetchone()
    if not row or row[0] == 0:
        default_poll = float(GLOBAL.get("interval", 5.0)) if isinstance(GLOBAL, dict) else 5.0
        default_reload = 30.0
        cur.execute(
            """
            INSERT INTO settings (id, poll_interval, db_reload_interval, telegram_chat_id, language)
            VALUES (1, ?, ?, NULL, 'en')
            """,
            (default_poll, default_reload),
        )


    conn.commit()
    conn.close()



def load_settings_from_db() -> Dict[str, Any]:
    """Lädt die globale Konfiguration aus der Tabelle `settings`.

    Gibt ein Dict mit Schlüsseln `poll_interval`, `db_reload_interval`,
    `telegram_chat_id` zurück.
    """
    settings: Dict[str, Any] = {}

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT poll_interval, db_reload_interval, telegram_chat_id, language FROM settings WHERE id = 1")
    row = cur.fetchone()
    conn.close()

    if row:
        default_poll = float(GLOBAL.get("interval", 5.0)) if isinstance(GLOBAL, dict) else 5.0
        settings["poll_interval"] = float(row["poll_interval"] or default_poll)
        settings["db_reload_interval"] = float(row["db_reload_interval"] or 30.0)
        settings["telegram_chat_id"] = row["telegram_chat_id"]
        settings["language"] = row["language"] or "en"
    else:
        settings["poll_interval"] = float(GLOBAL.get("interval", 5.0)) if isinstance(GLOBAL, dict) else 5.0
        settings["db_reload_interval"] = 30.0
        settings["telegram_chat_id"] = None
        settings["language"] = "en"

    return settings


def load_printers_from_db() -> list[dict]:
    """Lädt alle aktiven Drucker aus der SQLite-Datenbank.

    Wenn noch keine Drucker eingetragen sind, wird eine leere Liste
    zurückgegeben und es werden keine Monitor-Threads gestartet.
    """
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM printers WHERE enabled = 1 ORDER BY id")
    rows = cur.fetchall()
    conn.close()

    printers: list[dict] = []

    # Default für error_report_interval aus GLOBAL
    if isinstance(GLOBAL, dict):
        default_err = float(GLOBAL.get("error_report_interval", 30.0))
    else:
        default_err = 30.0

    for r in rows:
        https_flag = bool(r["https"])

        err_interval = (
            float(r["error_report_interval"])
            if r["error_report_interval"] is not None
            else default_err
        )

        printers.append(
            {
                "id": r["id"],
                "name": r["name"],
                "backend": r["backend"],
                "host": r["host"],
                "port": r["port"],
                "https": https_flag,
                "token": r["token"],
                "api_key": r["api_key"],
                "error_report_interval": err_interval,
                # Platzhalter-Felder für spätere Nutzung
                "tasmota_host": r["tasmota_host"],
                "tasmota_topic": r["tasmota_topic"],
            }
        )
    return printers

def get_printer_by_id(printer_id: int) -> Optional[sqlite3.Row]:
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM printers WHERE id = ?", (printer_id,))
    row = cur.fetchone()
    conn.close()
    return row


def load_translations(lang_code: str) -> dict:
    """Lädt Übersetzungen aus JSON-Dateien mit Fallback auf Englisch."""
    translations: Dict[str, Any] = {}

    # 1) Basis: Englisch immer laden
    en_path = os.path.join(I18N_DIR, "en.json")
    if os.path.exists(en_path):
        try:
            with open(en_path, "r", encoding="utf-8") as f:
                translations = json.load(f)
        except Exception as e:
            print(f"[i18n] Fehler beim Laden von en.json: {e}", file=sys.stderr)

    # 2) Gewünschte Sprache darüberlegen (falls nicht englisch)
    if lang_code != "en":
        lang_path = os.path.join(I18N_DIR, f"{lang_code}.json")
        if os.path.exists(lang_path):
            try:
                with open(lang_path, "r", encoding="utf-8") as f:
                    specific = json.load(f)
                translations.update(specific)
            except Exception as e:
                print(f"[i18n] Fehler beim Laden von {lang_code}.json: {e}", file=sys.stderr)

    return translations


def get_current_language() -> str:
    """Aktuelle Sprache aus den geladenen SETTINGS ermitteln."""
    lang = SETTINGS.get("language") or "en"
    return lang


def _(key: str) -> str:
    """Übersetzungsfunktion für Jinja-Templates."""
    if not hasattr(g, "translations"):
        return key
    return g.translations.get(key, key)


@app.before_request
def set_language():
    """Vor jedem Request Sprache setzen und Übersetzungen laden."""
    lang = get_current_language()
    g.lang = lang
    g.translations = load_translations(lang)


@app.context_processor
def inject_translation_helpers():
    """Stellt _() und current_language() in allen Templates zur Verfügung."""
    return {
        "_": _,
        "current_language": lambda: getattr(g, "lang", "en"),
    }


# DB-Struktur anlegen und initiale Daten laden
init_db_schema_only()
SETTINGS: Dict[str, Any] = load_settings_from_db()
PRINTERS = load_printers_from_db()




# aktive Monitor-Threads nach Drucker-ID
monitor_threads: Dict[int, threading.Thread] = {}


# ----------------- Helfer -----------------

def fmt_hms(seconds: float) -> str:
    s = int(seconds or 0)
    h, m, s2 = s // 3600, (s % 3600) // 60, s % 60
    return f"{h}:{m:02d}:{s2:02d} h" if h > 0 else f"{m:02d}:{s2:02d} min"


def progress_bar_pct(progress: float) -> float:
    return round(max(0.0, min(1.0, float(progress or 0.0))) * 100.0, 1)


def _num(x):
    try:
        return float(x)
    except Exception:
        return 0.0


# ----------------- Backends -----------------

def fetch_moonraker(base_url: str, token: Optional[str], timeout: float):
    path = (
        "/printer/objects/query?"
        "print_stats=state,filename,print_duration"
        "&virtual_sdcard=progress"
        "&extruder=temperature,target"
        "&heater_bed=temperature,target"
    )
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    r = requests.get(base_url + path, headers=headers, timeout=timeout)
    r.raise_for_status()
    data = r.json().get("result", {}).get("status", {})

    ps = data.get("print_stats", {}) or {}
    vsd = data.get("virtual_sdcard", {}) or {}
    ext = data.get("extruder", {}) or {}
    bed = data.get("heater_bed", {}) or {}

    state = ps.get("state", "unknown")
    filename = ps.get("filename", "") or ""
    elapsed = _num(ps.get("print_duration", 0.0))
    progress = _num(vsd.get("progress", 0.0))

    hotend = _num(ext.get("temperature"))
    hotend_t = _num(ext.get("target"))
    bed_c = _num(bed.get("temperature"))
    bed_t = _num(bed.get("target"))
    return (state, filename, elapsed, progress, hotend, hotend_t, bed_c, bed_t)


def fetch_octoprint(base_url: str, api_key: str, timeout: float):
    headers = {"X-Api-Key": api_key}
    r_job = requests.get(base_url + "/api/job", headers=headers, timeout=timeout)
    r_job.raise_for_status()
    job = r_job.json()

    r_prn = requests.get(base_url + "/api/printer", headers=headers, timeout=timeout)
    r_prn.raise_for_status()
    prn = r_prn.json()

    state_text = job.get("state") or ""
    progress = (job.get("progress", {}) or {}).get("completion")
    progress01 = (progress / 100.0) if isinstance(progress, (int, float)) else 0.0
    elapsed = _num((job.get("progress", {}) or {}).get("printTime"))
    filename = ""
    try:
        filename = job.get("job", {}).get("file", {}).get("name") or ""
    except Exception:
        pass

    tool0 = (prn.get("temperature", {}) or {}).get("tool0", {}) or {}
    bed = (prn.get("temperature", {}) or {}).get("bed", {}) or {}
    hotend = _num(tool0.get("actual"))
    hotend_t = _num(tool0.get("target"))
    bed_c = _num(bed.get("actual"))
    bed_t = _num(bed.get("target"))

    st = state_text.lower()
    if "printing" in st or "in progress" in st:
        state = "printing"
    elif "paused" in st:
        state = "paused"
    elif "cancelling" in st or "cancelled" in st:
        state = "cancelled"
    elif any(k in st for k in ("complete", "finished", "done")):
        state = "complete"
    elif any(k in st for k in ("error", "offline", "closed")):
        state = "error"
    else:
        state = "standby"

    return (state, filename, elapsed, progress01, hotend, hotend_t, bed_c, bed_t)


# ----------------- Monitor-Thread -----------------

def monitor_printer(prn: dict, printer_id: int, global_defaults: dict, stop_evt: threading.Event):
    global SETTINGS

    name = prn.get("name", prn.get("host", "UNNAMED"))
    host = prn["host"]
    port = prn.get("port", global_defaults.get("port", 80))
    https = prn.get("https", global_defaults.get("https", False))
    be = (prn.get("backend") or "moonraker").lower()
    token = prn.get("token")
    api_key = prn.get("api_key")

    # aktueller Tasmota-Host, wird im Loop aus der DB aktualisiert
    current_tasmota_host = prn.get("tasmota_host")


    # robuster Default für error_report_interval
    if isinstance(global_defaults, dict):
        default_err = float(global_defaults.get("error_report_interval", 30.0))
    else:
        default_err = 30.0

    err_raw = prn.get("error_report_interval")
    if err_raw is None:
        err_raw = default_err
    err_interval = float(err_raw)

    scheme = "https" if https else "http"
    base_url = f"{scheme}://{host}:{port}"

    consecutive_errors = 0
    last_error_report_ts = 0.0
    last_error_text = None

    while not stop_evt.is_set():

        # prüfen ob Drucker noch aktiv ist + Tasmota-Host aus DB holen
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("SELECT enabled, tasmota_host FROM printers WHERE id = ?", (printer_id,))
            row = cur.fetchone()
            conn.close()
            if (row is None) or (row["enabled"] != 1):
                print(f"[{name}] Deaktiviert oder gelöscht – beende Monitor-Thread.", file=sys.stderr)
                break

            # NEU: aktuellen Tasmota-Host aus der DB übernehmen
            current_tasmota_host = row["tasmota_host"]

        except Exception as e:
            print(f"[{name}] Warnung: Konnte enabled-Status/Tasmota-Host nicht prüfen: {e}", file=sys.stderr)


        # Poll-Intervall
        poll_default = float(GLOBAL.get("interval", 5.0)) if isinstance(GLOBAL, dict) else 5.0
        poll_interval = float(SETTINGS.get("poll_interval", poll_default))

        try:
            # Backend-Abfrage
            if be == "octoprint":
                res = fetch_octoprint(
                    base_url,
                    api_key=api_key,
                    timeout=max(5.0, poll_interval + 2.0),
                )
            else:
                res = fetch_moonraker(
                    base_url,
                    token=token,
                    timeout=max(5.0, poll_interval + 2.0),
                )

            state, filename, elapsed, progress, hotend, hotend_t, bed, bed_t = res

            eta_s = 0.0
            if progress and progress > 0 and elapsed and elapsed > 0:
                eta_s = elapsed * (1.0 / progress - 1.0)

            with state_lock:
                printer_state[name] = {
                    "id": printer_id,
                    "name": name,
                    "backend": be,
                    "host": host,
                    "state": state,
                    "filename": filename,
                    "progress_pct": progress_bar_pct(progress),
                    "elapsed_s": float(elapsed),
                    "eta_s": float(eta_s),
                    "elapsed_hms": fmt_hms(elapsed),
                    "eta_hms": fmt_hms(eta_s),
                    "hotend": round(hotend, 1),
                    "hotend_t": round(hotend_t, 1),
                    "bed": round(bed, 1),
                    "bed_t": round(bed_t, 1),
                    "last_update": int(time.time()),
                    "error": None,
                    "link": f"{scheme}://{host}:{port}/",
                    "tasmota_host": current_tasmota_host,
                }

            consecutive_errors = 0
            last_error_text = None
            last_error_report_ts = 0.0

        except requests.exceptions.RequestException as e:
            # Offline
            consecutive_errors += 1
            err = f"NICHT ERREICHBAR (Versuch {consecutive_errors}): {e}"
            now = time.time()

            with state_lock:
                st = printer_state.get(
                    name,
                    {
                        "id": printer_id,
                        "name": name,
                        "backend": be,
                        "host": host,
                        "tasmota_host": current_tasmota_host,
                    },
                )
                st.update(
                    {
                        "state": "offline",
                        "filename": "",
                        "progress_pct": 0.0,
                        "elapsed_s": 0.0,
                        "eta_s": 0.0,
                        "elapsed_hms": "00:00 min",
                        "eta_hms": "00:00 min",
                        "hotend": 0.0,
                        "hotend_t": 0.0,
                        "bed": 0.0,
                        "bed_t": 0.0,
                        "last_update": int(now),
                        "error": err,
                        "link": f"{scheme}://{host}:{port}/",
                    }
                )
                printer_state[name] = st

            if (
                (consecutive_errors == 1)
                or (err != last_error_text)
                or (now - last_error_report_ts >= err_interval)
            ):
                print(f"[{name}] {err}", file=sys.stderr)
                last_error_text = err
                last_error_report_ts = now

        except Exception as e:
            # unerwarteter Fehler
            consecutive_errors += 1
            err = f"Unerwarteter Fehler: {e}"
            now = time.time()

            with state_lock:
                st = printer_state.get(
                    name,
                    {
                        "id": printer_id,
                        "name": name,
                        "backend": be,
                        "host": host,
                        "tasmota_host": current_tasmota_host,
                    },
                )
                st.update(
                    {
                        "state": "error",
                        "filename": "",
                        "progress_pct": 0.0,
                        "elapsed_s": 0.0,
                        "eta_s": 0.0,
                        "elapsed_hms": "00:00 min",
                        "eta_hms": "00:00 min",
                        "hotend": 0.0,
                        "hotend_t": 0.0,
                        "bed": 0.0,
                        "bed_t": 0.0,
                        "last_update": int(now),
                        "error": err,
                        "link": f"{scheme}://{host}:{port}/",
                    }
                )
                printer_state[name] = st

            if (
                (consecutive_errors == 1)
                or (err != last_error_text)
                or (now - last_error_report_ts >= err_interval)
            ):
                print(f"[{name}] {err}", file=sys.stderr)
                last_error_text = err
                last_error_report_ts = now

        # Schleifenpause
        time.sleep(max(0.2, poll_interval))

# ----------------- DB-Watcher-Thread -----------------

def db_watch_loop(global_stop_evt: threading.Event):
    """Beobachtet periodisch die Datenbank:

    - Lädt geänderte Settings (poll_interval, db_reload_interval, telegram_chat_id)
    - Startet Monitor-Threads für neu hinzugefügte Drucker (enabled = 1)

    Dadurch muss das Script bei neuen Druckern oder geänderten Settings
    nicht neu gestartet werden.
    """
    global SETTINGS, PRINTERS, monitor_threads

    while not global_stop_evt.is_set():
        try:
            # Settings aktualisieren
            SETTINGS = load_settings_from_db()

            # Drucker neu laden
            PRINTERS = load_printers_from_db()

            # Neue Drucker erkennen und ggf. Monitor-Thread starten
            for prn in PRINTERS:
                pid = prn["id"]
                if pid not in monitor_threads or not monitor_threads[pid].is_alive():
                    t = threading.Thread(
                        target=monitor_printer,
                        args=(prn, pid, GLOBAL if isinstance(GLOBAL, dict) else {}, global_stop_evt),
                        daemon=True,
                    )
                    t.start()
                    monitor_threads[pid] = t

        except Exception as e:
            print(f"[DB-WATCHER] Fehler beim Reload: {e}", file=sys.stderr)

        # Reload-Intervall aus SETTINGS
        reload_interval = float(SETTINGS.get("db_reload_interval", 30.0)) if SETTINGS else 30.0
        time.sleep(max(5.0, reload_interval))


# ----------------- Flask Endpoints -----------------


@app.route("/")
def index() -> str:
    # 'page' wird im Template benutzt, um den aktiven Menüpunkt zu markieren
    return render_template("index.html", page="overview")


@app.route("/settings", methods=["GET", "POST"])
def settings_page() -> str:
    """Globale Einstellungen (Settings-Tabelle) über ein Formular verwalten."""
    global SETTINGS

    error = None
    message = None

    # Startwerte aus den aktuell geladenen SETTINGS
    current_poll = float(SETTINGS.get("poll_interval", 5.0))
    current_reload = float(SETTINGS.get("db_reload_interval", 30.0))
    current_chat_id = SETTINGS.get("telegram_chat_id") or ""
    current_lang = SETTINGS.get("language", "en")

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

            # Globale SETTINGS neu laden, damit Threads neue Werte nutzen
            SETTINGS = load_settings_from_db()
            message = "Einstellungen gespeichert."

            # Form-Werte an die neu geladenen Einstellungen anpassen
            form_values["poll_interval"] = SETTINGS.get("poll_interval", poll)
            form_values["db_reload_interval"] = SETTINGS.get("db_reload_interval", reload_interval)
            form_values["telegram_chat_id"] = SETTINGS.get("telegram_chat_id") or ""
            form_values["language"] = SETTINGS.get("language", language)

    return render_template(
        "settings.html",
        page="settings",
        settings=form_values,
        error=error,
        message=message,
    )



@app.route("/printers")
def printer_list() -> str:
    """Liste aller Drucker anzeigen."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM printers ORDER BY id")
    printers = cur.fetchall()
    conn.close()
    return render_template("printers_list.html", page="printers", printers=printers)


@app.route("/printers/new", methods=["GET", "POST"])
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
        # NEU: Tasmota-IP-Adresse
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
            return redirect(url_for("printer_edit", printer_id=new_id))

    # GET oder Fehlerfall
    return render_template("printer_form.html", page="printers", printer=None, error=error, mode="new")



@app.route("/printers/<int:printer_id>", methods=["GET", "POST"])
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
        # NEU: Tasmota-IP-Adresse
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

    return render_template("printer_form.html", page="printers", printer=printer, error=error, mode="edit")



@app.route("/printers/<int:printer_id>/delete", methods=["POST"])
def printer_delete(printer_id: int):
    """Drucker endgültig löschen."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM printers WHERE id = ?", (printer_id,))
    conn.commit()
    conn.close()
    # Liste neu anzeigen
    return redirect(url_for("printer_list"))

@app.route("/api/printer/<int:printer_id>/power/status")
def api_printer_power_status(printer_id):
    printer = get_printer_by_id(printer_id)
    if printer is None:
        return jsonify({"status": "error", "msg": "Printer not found"}), 404

    ip = printer["tasmota_host"]
    if not ip:
        return jsonify({"status": "error", "msg": "No Tasmota IP configured"}), 400

    state = tasmota_get_state(ip)  # 'ON', 'OFF', 'UNKNOWN'
    return jsonify({"status": "ok", "state": state})


@app.route("/api/printer/<int:printer_id>/power/toggle", methods=["POST"])
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

    return jsonify({
        "status": "ok" if ok else "error",
        "requested": target_state,
        "state": new_state
    }), (200 if ok else 500)



@app.route("/api/status")
def api_status():
    with state_lock:
        rows = [printer_state[k] for k in sorted(printer_state.keys())]
    return jsonify(rows)


@app.route("/debug_routes")
def debug_routes():
    lines = []
    for rule in app.url_map.iter_rules():
        lines.append(f"{rule.endpoint} -> {rule.rule}")
    return "<br>".join(sorted(lines))



# ----------------- Start Threads + App -----------------

def start_monitor_threads(initial_printers: list[dict]):
    stop_evt = threading.Event()
    for prn in initial_printers:
        pid = prn["id"]
        t = threading.Thread(
            target=monitor_printer,
            args=(prn, pid, GLOBAL if isinstance(GLOBAL, dict) else {}, stop_evt),
            daemon=True,
        )
        t.start()
        monitor_threads[pid] = t
    return stop_evt


if __name__ == "__main__":

    # Initiale Platzhalter für vorhandene Drucker
    with state_lock:
        for prn in PRINTERS:
            name = prn.get("name", prn.get("host", "UNNAMED"))
            host = prn["host"]
            port = prn.get("port", GLOBAL.get("port", 80)) if isinstance(GLOBAL, dict) else prn.get("port", 80)
            https = prn.get("https", GLOBAL.get("https", False)) if isinstance(GLOBAL, dict) else prn.get("https", False)
            scheme = "https" if https else "http"

            printer_state[name] = {
                "id": prn["id"],                     # korrekt
                "name": name,
                "backend": prn.get("backend", "moonraker"),
                "host": host,
                "state": "standby",
                "filename": "",
                "progress_pct": 0.0,
                "elapsed_s": 0.0,
                "eta_s": 0.0,
                "elapsed_hms": "00:00 min",
                "eta_hms": "00:00 min",
                "hotend": 0.0,
                "hotend_t": 0.0,
                "bed": 0.0,
                "bed_t": 0.0,
                "last_update": int(time.time()),
                "error": None,
                "link": f"{scheme}://{host}:{port}/",
                "tasmota_host": prn.get("tasmota_host"),   # korrekt
            }

    # Monitor-Threads starten
    global_stop_evt = start_monitor_threads(PRINTERS)

    # DB-Watcher starten
    watcher_thread = threading.Thread(
        target=db_watch_loop,
        args=(global_stop_evt,),
        daemon=True,
    )
    watcher_thread.start()

    try:
        app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
    finally:
        global_stop_evt.set()
        for t in list(monitor_threads.values()):
            t.join(timeout=2.0)
        watcher_thread.join(timeout=2.0)