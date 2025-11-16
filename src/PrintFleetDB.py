#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time
import sys
import threading
import requests
import sqlite3
import os
from typing import Optional, Dict, Any

from flask import Flask, jsonify, render_template

# -------------------------------------------------
# Konfiguration laden (nur GLOBAL)
# -------------------------------------------------
try:
    from PrintFleetPrinterList import GLOBAL
except Exception as e:
    print("Konfigurationsdatei 'PrintFleetPrinterList.py' fehlt/fehlerhaft.", file=sys.stderr)
    raise


# -------------------------------------------------
# SQLite: nur Struktur anlegen, keine Seed-Daten
# -------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "PrintFleet.sqlite3")


def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db_schema_only() -> None:
    """Erzeugt (falls nötig) die Tabelle `printers`.

    Es werden **keine** Drucker aus einer Python-Liste übernommen.
    Die Datenpflege erfolgt extern (z.B. mit einem DB-Tool) und wird später
    um ein Web-Formular in PrintFleet ergänzt.
    """
    conn = get_db_connection()
    cur = conn.cursor()

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
            interval REAL,
            error_report_interval REAL,
            -- Platzhalter für spätere Erweiterungen
            tasmota_host TEXT,
            tasmota_topic TEXT,
            telegram_chat_id TEXT,
            enabled INTEGER NOT NULL DEFAULT 1
        );
        """
    )

    conn.commit()
    conn.close()


def load_printers_from_db() -> list[dict]:
    """Lädt alle aktiven Drucker aus der SQLite-Datenbank.

    Die Struktur der zurückgegebenen Dicts entspricht den geplanten
    Konfigurationsfeldern, sodass der Rest des Codes unverändert
    weiterarbeiten kann.

    Wenn noch keine Drucker eingetragen sind, wird eine leere Liste
    zurückgegeben und es werden keine Monitor-Threads gestartet.
    """
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM printers WHERE enabled = 1 ORDER BY id")
    rows = cur.fetchall()
    conn.close()

    printers: list[dict] = []
    for r in rows:
        https_flag = bool(r["https"])
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
                # Falls nicht gesetzt, auf GLOBAL zurückfallen
                "interval": r["interval"]
                if r["interval"] is not None
                else float(GLOBAL.get("interval", 5.0)),
                "error_report_interval": r["error_report_interval"]
                if r["error_report_interval"] is not None
                else float(GLOBAL.get("error_report_interval", 30.0)),
                # Platzhalter-Felder für spätere Nutzung
                "tasmota_host": r["tasmota_host"],
                "tasmota_topic": r["tasmota_topic"],
                "telegram_chat_id": r["telegram_chat_id"],
            }
        )
    return printers


# DB-Struktur anlegen und Druckerliste aus DB holen
init_db_schema_only()
PRINTERS = load_printers_from_db()


# -------------------------------------------------
# Flask-App mit Template- und Static-Ordner
# -------------------------------------------------
app = Flask(__name__, static_folder="static", template_folder="templates")

state_lock = threading.Lock()
printer_state: Dict[str, Dict[str, Any]] = {}


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

def monitor_printer(prn: dict, global_defaults: dict, stop_evt: threading.Event):
    name = prn.get("name", prn.get("host", "UNNAMED"))
    host = prn["host"]
    port = prn.get("port", global_defaults.get("port", 80))
    https = prn.get("https", global_defaults.get("https", False))
    be = (prn.get("backend") or "moonraker").lower()
    token = prn.get("token")
    api_key = prn.get("api_key")
    interval = float(prn.get("interval", global_defaults.get("interval", 5.0)))
    err_interval = float(
        prn.get("error_report_interval", global_defaults.get("error_report_interval", 30.0))
    )

    scheme = "https" if https else "http"
    base_url = f"{scheme}://{host}:{port}"

    consecutive_errors = 0
    last_error_report_ts = 0.0
    last_error_text = None

    while not stop_evt.is_set():
        try:
            if be == "octoprint":
                res = fetch_octoprint(
                    base_url,
                    api_key=api_key,
                    timeout=max(5.0, interval + 2.0),
                )
            else:
                res = fetch_moonraker(
                    base_url,
                    token=token,
                    timeout=max(5.0, interval + 2.0),
                )

            (
                state,
                filename,
                elapsed,
                progress,
                hotend,
                hotend_t,
                bed,
                bed_t,
            ) = res

            eta_s = 0.0
            if progress and progress > 0 and elapsed and elapsed > 0:
                eta_s = elapsed * (1.0 / progress - 1.0)

            with state_lock:
                printer_state[name] = {
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
                }

            consecutive_errors = 0
            last_error_text = None
            last_error_report_ts = 0.0

        except requests.exceptions.RequestException as e:
            consecutive_errors += 1
            err = f"NICHT ERREICHBAR (Versuch {consecutive_errors}): {e}"
            now = time.time()
            with state_lock:
                st = printer_state.get(
                    name, {"name": name, "backend": be, "host": host}
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
            consecutive_errors += 1
            err = f"Unerwarteter Fehler: {e}"
            now = time.time()
            with state_lock:
                st = printer_state.get(
                    name, {"name": name, "backend": be, "host": host}
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

        time.sleep(max(0.2, interval))


# ----------------- Flask Endpoints -----------------


@app.route("/")
def index() -> str:
    # 'page' wird im Template benutzt, um den aktiven Menüpunkt zu markieren
    return render_template("index.html", page="overview")


@app.route("/settings")
def settings_page() -> str:
    # Beispiel für eine weitere Seite, die du über das Menü erreichst
    return render_template("settings.html", page="settings")


@app.route("/api/status")
def api_status():
    with state_lock:
        rows = [printer_state[k] for k in sorted(printer_state.keys())]
    return jsonify(rows)


# ----------------- Start Threads + App -----------------

def start_threads():
    stop_evt = threading.Event()
    threads = []
    for prn in PRINTERS:
        t = threading.Thread(
            target=monitor_printer,
            args=(prn, GLOBAL if isinstance(GLOBAL, dict) else {}, stop_evt),
            daemon=True,
        )
        t.start()
        threads.append(t)
    return stop_evt, threads


if __name__ == "__main__":
    # Initiale Platzhalter (auf Basis der in der DB hinterlegten Drucker)
    with state_lock:
        for prn in PRINTERS:
            name = prn.get("name", prn.get("host", "UNNAMED"))
            host = prn["host"]
            port = prn.get("port", GLOBAL.get("port", 80))
            https = prn.get("https", GLOBAL.get("https", False))
            scheme = "https" if https else "http"
            printer_state[name] = {
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
            }

    stop_evt, threads = start_threads()
    try:
        app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
    finally:
        stop_evt.set()
        for t in threads:
            t.join(timeout=2.0)