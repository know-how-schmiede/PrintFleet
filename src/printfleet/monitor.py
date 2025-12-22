#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time
import sys
import threading
from typing import Dict, Any, Optional

import requests

from printfleet.db import get_db_connection, load_settings_from_db, load_printers_from_db
from printfleet.state import state_lock, printer_state
from printfleet.backends import (
    fetch_moonraker,
    fetch_octoprint,
    fetch_centauri,
)


# Konfiguration (GLOBAL) aus der bestehenden Datei laden
try:
    from PrintFleetPrinterList import GLOBAL
except Exception as e:
    print("Konfigurationsdatei 'PrintFleetPrinterList.py' fehlt/fehlerhaft (monitor).", file=sys.stderr)
    GLOBAL = {}


# ----------------- Helfer -----------------

def fmt_hms(seconds: float) -> str:
    s = int(seconds or 0)
    h, m, s2 = s // 3600, (s % 3600) // 60, s % 60
    return f"{h}:{m:02d}:{s2:02d} h" if h > 0 else f"{m:02d}:{s2:02d} min"


def progress_bar_pct(progress: float) -> float:
    return round(max(0.0, min(1.0, float(progress or 0.0))) * 100.0, 1)


def build_no_scanning_state(prn: dict, name: str, host: str, port: int, https: bool) -> dict:
    scheme = "https" if https else "http"
    return {
        "id": prn.get("id"),
        "name": name,
        "backend": (prn.get("backend") or "moonraker"),
        "host": host,
        "state": "no_scanning",
        "filename": "",
        "progress_pct": 0.0,
        "elapsed_s": 0.0,
        "eta_s": 0.0,
        "elapsed_hms": "",
        "eta_hms": "",
        "hotend": None,
        "hotend_t": None,
        "bed": None,
        "bed_t": None,
        "last_update": 0,
        "error": None,
        "link": f"{scheme}://{host}:{port}/",
        "tasmota_host": prn.get("tasmota_host"),
        "no_scanning": True,
    }


# ----------------- Monitor-Thread -----------------

def monitor_printer(
    prn: dict,
    printer_id: int,
    global_defaults: dict,
    stop_evt: threading.Event,
) -> None:
    """
    Pollt einen einzelnen Drucker periodisch und schreibt den Status in printer_state.
    Läuft in einem eigenen Thread.
    """
    name = prn.get("name", prn.get("host", "UNNAMED"))
    host = prn["host"]
    port = prn.get("port", global_defaults.get("port", 80))
    https = prn.get("https", global_defaults.get("https", False))
    be = (prn.get("backend") or "moonraker").lower()
    token = prn.get("token")
    api_key = prn.get("api_key")

    # aktueller Tasmota-Host, wird im Loop aus der DB nachgeladen
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
    last_error_text: Optional[str] = None

    while not stop_evt.is_set():
        # prüfen ob Drucker noch aktiv ist + Tasmota-Host aus DB holen
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute(
                "SELECT enabled, tasmota_host, no_scanning, host, port, https FROM printers WHERE id = ?",
                (printer_id,),
            )
            row = cur.fetchone()
            conn.close()
            if (row is None) or (row["enabled"] != 1):
                print(f"[{name}] Deaktiviert oder gelöscht – beende Monitor-Thread.", file=sys.stderr)
                
                # Zustand aus printer_state entfernen
                with state_lock:
                    printer_state.pop(name, None)
                
                break

            current_tasmota_host = row["tasmota_host"]

            if row["no_scanning"] == 1:
                prn["tasmota_host"] = current_tasmota_host
                host = row["host"] or host
                port = row["port"] or port
                https = bool(row["https"]) if row["https"] is not None else https
                with state_lock:
                    printer_state[name] = build_no_scanning_state(prn, name, host, port, https)
                break

        except Exception as e:
            print(f"[{name}] Warnung: Konnte enabled-Status/Tasmota-Host nicht prüfen: {e}", file=sys.stderr)

        # Poll-Intervall aus Settings (immer frisch aus DB)
        try:
            settings = load_settings_from_db()
            poll_default = float(GLOBAL.get("interval", 5.0)) if isinstance(GLOBAL, dict) else 5.0
            poll_interval = float(settings.get("poll_interval", poll_default))
        except Exception:
            poll_default = float(GLOBAL.get("interval", 5.0)) if isinstance(GLOBAL, dict) else 5.0
            poll_interval = poll_default

        try:
            # Backend-Abfrage
            if be == "octoprint":
                res = fetch_octoprint(
                    base_url,
                    api_key=api_key,
                    timeout=max(5.0, poll_interval + 2.0),
                )
            elif be in ("centauri", "centurio", "centuri", "elegoo"):
                # Elegoo Centurio / Centauri Carbon (WebSocket-Backend)
                centauri_timeout = max(10.0, poll_interval * 2.0)
                res = fetch_centauri(
                    base_url,
                    timeout=centauri_timeout,
                )
            else:
                # Standard: Moonraker / Klipper
                res = fetch_moonraker(
                    base_url,
                    token=token,
                    timeout=max(5.0, poll_interval + 2.0),
                )

        

            state, filename, elapsed, progress, hotend, hotend_t, bed, bed_t = res

            # ---- Centauri: "printing" nicht unnötig auf "standby" zurückfallen lassen ----
            if be in ("centauri", "centurio", "centuri", "elegoo"):
                try:
                    prev = printer_state.get(name)
                except Exception:
                    prev = None

                # Wenn wir vorher schon "printing" waren und jetzt "standby" wären,
                # aber noch Heizphase / echter Fortschritt erkennbar ist:
                # "printing" beibehalten.
                if (
                    prev
                    and prev.get("state") == "printing"
                    and state == "standby"
                    and (
                        progress > 0.0      # es gibt schon Fortschritt
                        or hotend_t > 0.0   # oder Nozzle-Zieltemp > 0
                        or bed_t > 0.0      # oder Bett-Zieltemp > 0
                    )
                ):
                    state = "printing"



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
                    "no_scanning": False,
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
                        "no_scanning": False,
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
            # unerwarteter Fehler (Backend-, JSON-, WebSocket-, sonstige Fehler)
            consecutive_errors += 1
            err = f"Unerwarteter Fehler im Backend '{be}' mit URL {base_url}: {e}"
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
                        "link": f"{scheme}://{host}:{port}/",
                    },
                )

                if be in ("centauri", "centurio", "centuri", "elegoo"):
                    # Für den Centauri: letzten gültigen Zustand behalten,
                    # nur Fehlertext und Zeitstempel aktualisieren
                    st["error"] = err
                    st["last_update"] = int(now)
                    st["no_scanning"] = False
                else:
                    # Für alle anderen Backends wie bisher hart auf "error" setzen
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
                            "no_scanning": False,
                        }
                    )

                printer_state[name] = st

            # Logging nur am Anfang oder wenn neue Meldung
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


# globale Map für Monitor-Threads in diesem Modul
monitor_threads: Dict[int, threading.Thread] = {}


def start_monitor_threads(initial_printers: list[dict], stop_evt: threading.Event) -> None:
    """
    Startet für alle übergebenen Drucker je einen Monitor-Thread.
    """
    global monitor_threads

    defaults = GLOBAL if isinstance(GLOBAL, dict) else {}

    for prn in initial_printers:
        pid = prn["id"]
        if pid in monitor_threads and monitor_threads[pid].is_alive():
            continue

        if prn.get("no_scanning"):
            name = prn.get("name", prn.get("host", "UNNAMED"))
            host = prn["host"]
            port = prn.get("port", defaults.get("port", 80))
            https = prn.get("https", defaults.get("https", False))
            with state_lock:
                printer_state[name] = build_no_scanning_state(prn, name, host, port, https)
            continue

        t = threading.Thread(
            target=monitor_printer,
            args=(prn, pid, defaults, stop_evt),
            daemon=True,
        )
        t.start()
        monitor_threads[pid] = t


def db_watch_loop(global_stop_evt: threading.Event) -> None:
    """
    Beobachtet periodisch die Datenbank:

    - Lädt geänderte Settings (z.B. db_reload_interval)
    - Startet Monitor-Threads für neu hinzugefügte Drucker (enabled = 1)
    """
    while not global_stop_evt.is_set():
        try:
            settings = load_settings_from_db()
            printers = load_printers_from_db()

            # neue Drucker erkennen und ggf. Monitor-Thread starten
            start_monitor_threads(printers, global_stop_evt)

        except Exception as e:
            print(f"[DB-WATCHER] Fehler beim Reload: {e}", file=sys.stderr)

        # Reload-Intervall aus Settings
        try:
            reload_interval = float(settings.get("db_reload_interval", 30.0))
        except Exception:
            reload_interval = 30.0

        time.sleep(max(5.0, reload_interval))


def create_initial_state(printers: list[dict]) -> None:
    """
    Initiale Platzhalter im printer_state für vorhandene Drucker anlegen.
    """
    with state_lock:
        for prn in printers:
            name = prn.get("name", prn.get("host", "UNNAMED"))
            host = prn["host"]

            if isinstance(GLOBAL, dict):
                port = prn.get("port", GLOBAL.get("port", 80))
                https = prn.get("https", GLOBAL.get("https", False))
            else:
                port = prn.get("port", 80)
                https = prn.get("https", False)

            if prn.get("no_scanning"):
                printer_state[name] = build_no_scanning_state(prn, name, host, port, https)
                continue

            scheme = "https" if https else "http"

            printer_state[name] = {
                "id": prn["id"],
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
                "tasmota_host": prn.get("tasmota_host"),
                "no_scanning": False,
            }


def join_monitor_threads(timeout: float = 2.0) -> None:
    """
    Alle Monitor-Threads mit Timeout joinen (für sauberes Herunterfahren).
    """
    for t in list(monitor_threads.values()):
        t.join(timeout=timeout)
