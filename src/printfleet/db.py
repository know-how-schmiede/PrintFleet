#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import sqlite3
from typing import Optional, Dict, Any

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

# Verzeichnisstruktur:
# Dieses File liegt unter src/printfleet/db.py
# PROJECT_ROOT zeigt auf src/
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)

DB_PATH = os.path.join(PROJECT_ROOT, "PrintFleet.sqlite3")


def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db_schema_only() -> None:
    """Erzeugt (falls nötig) die Tabellen `printers` und `settings`."""

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
    """Lädt die globale Konfiguration aus der Tabelle `settings`."""
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
    """Lädt alle aktiven Drucker aus der SQLite-Datenbank."""
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