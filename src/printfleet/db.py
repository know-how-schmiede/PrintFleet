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
    """Erzeugt (falls nötig) die Tabellen `printers` und `settings`
    und führt einfache Migrationen für neue Spalten durch.
    """
    conn = get_db_connection()
    cur = conn.cursor()

    # ---------------------------
    # printers: Ziel-Schema
    # ---------------------------
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS printers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            backend TEXT NOT NULL,
            host TEXT NOT NULL,
            port INTEGER NOT NULL,
            https INTEGER NOT NULL DEFAULT 0,
            no_scanning INTEGER NOT NULL DEFAULT 0,
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

    # Migration für bestehende Installationen (printers)
    cur.execute("PRAGMA table_info(printers)")
    printer_cols = [r[1] for r in cur.fetchall()]

    if "error_report_interval" not in printer_cols:
        cur.execute("ALTER TABLE printers ADD COLUMN error_report_interval REAL NOT NULL DEFAULT 30.0")

    if "tasmota_host" not in printer_cols:
        cur.execute("ALTER TABLE printers ADD COLUMN tasmota_host TEXT")

    if "no_scanning" not in printer_cols:
        cur.execute("ALTER TABLE printers ADD COLUMN no_scanning INTEGER NOT NULL DEFAULT 0")

    if "tasmota_topic" not in printer_cols:
        cur.execute("ALTER TABLE printers ADD COLUMN tasmota_topic TEXT")

    if "location" not in printer_cols:
        cur.execute("ALTER TABLE printers ADD COLUMN location TEXT")

    if "printer_type" not in printer_cols:
        cur.execute("ALTER TABLE printers ADD COLUMN printer_type TEXT")

    if "notes" not in printer_cols:
        cur.execute("ALTER TABLE printers ADD COLUMN notes TEXT")

    if "enabled" not in printer_cols:
        cur.execute("ALTER TABLE printers ADD COLUMN enabled INTEGER NOT NULL DEFAULT 1")

    # ---------------------------
    # settings: Ziel-Schema
    # ---------------------------
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            poll_interval REAL,
            db_reload_interval REAL,
            telegram_chat_id TEXT,
            language TEXT,
            imprint_markdown TEXT,
            privacy_markdown TEXT
        );
        """
    )

    # ---------------------------
    # users: Ziel-Schema
    # ---------------------------
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    )

    # Migration für bestehende Installationen (settings)
    cur.execute("PRAGMA table_info(settings)")
    settings_cols = [r[1] for r in cur.fetchall()]

    if "language" not in settings_cols:
        cur.execute("ALTER TABLE settings ADD COLUMN language TEXT")

    if "imprint_markdown" not in settings_cols:
        cur.execute("ALTER TABLE settings ADD COLUMN imprint_markdown TEXT")

    if "privacy_markdown" not in settings_cols:
        cur.execute("ALTER TABLE settings ADD COLUMN privacy_markdown TEXT")

    # Falls noch kein Settings-Datensatz existiert, einen Default-Eintrag erzeugen
    cur.execute("SELECT COUNT(*) AS cnt FROM settings")
    row = cur.fetchone()
    if not row or row[0] == 0:
        default_poll = float(GLOBAL.get("interval", 5.0)) if isinstance(GLOBAL, dict) else 5.0
        default_reload = 30.0
        cur.execute(
            """
            INSERT INTO settings (
                id,
                poll_interval,
                db_reload_interval,
                telegram_chat_id,
                language,
                imprint_markdown,
                privacy_markdown
            )
            VALUES (1, ?, ?, NULL, 'en', NULL, NULL)
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
    cur.execute(
        """
        SELECT
            poll_interval,
            db_reload_interval,
            telegram_chat_id,
            language,
            imprint_markdown,
            privacy_markdown
        FROM settings
        WHERE id = 1
        """
    )
    row = cur.fetchone()
    conn.close()

    if row:
        default_poll = float(GLOBAL.get("interval", 5.0)) if isinstance(GLOBAL, dict) else 5.0
        settings["poll_interval"] = float(row["poll_interval"] or default_poll)
        settings["db_reload_interval"] = float(row["db_reload_interval"] or 30.0)
        settings["telegram_chat_id"] = row["telegram_chat_id"]
        settings["language"] = row["language"] or "en"
        settings["imprint_markdown"] = row["imprint_markdown"] or ""
        settings["privacy_markdown"] = row["privacy_markdown"] or ""
    else:
        settings["poll_interval"] = float(GLOBAL.get("interval", 5.0)) if isinstance(GLOBAL, dict) else 5.0
        settings["db_reload_interval"] = 30.0
        settings["telegram_chat_id"] = None
        settings["language"] = "en"
        settings["imprint_markdown"] = ""
        settings["privacy_markdown"] = ""

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
                "no_scanning": bool(r["no_scanning"]) if "no_scanning" in r.keys() else False,
                "token": r["token"],
                "api_key": r["api_key"],
                "error_report_interval": err_interval,
                # Power / Tasmota
                "tasmota_host": r["tasmota_host"],
                "tasmota_topic": r["tasmota_topic"],
                # Metadaten
                "location": r["location"],
                "printer_type": r["printer_type"],
                "notes": r["notes"],
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


def count_users() -> int:
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) AS cnt FROM users")
    row = cur.fetchone()
    conn.close()
    return int(row["cnt"] if row else 0)


def get_user_by_username(username: str) -> Optional[sqlite3.Row]:
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE username = ?", (username,))
    row = cur.fetchone()
    conn.close()
    return row


def get_user_by_id(user_id: int) -> Optional[sqlite3.Row]:
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return row


def create_user(username: str, password_hash: str) -> int:
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO users (username, password_hash) VALUES (?, ?)",
        (username, password_hash),
    )
    conn.commit()
    user_id = cur.lastrowid
    conn.close()
    return int(user_id)


def update_user_password(user_id: int, password_hash: str) -> None:
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE users SET password_hash = ? WHERE id = ?",
        (password_hash, user_id),
    )
    conn.commit()
    conn.close()


def delete_user(user_id: int) -> None:
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()


def list_users() -> list[dict]:
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, username, created_at FROM users ORDER BY username")
    rows = cur.fetchall()
    conn.close()
    return [
        {"id": r["id"], "username": r["username"], "created_at": r["created_at"]}
        for r in rows
    ]
