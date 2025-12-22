#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import Optional, Dict, Any

from printfleet.version import APP_VERSION as PRINTFLEET_VERSION
from printfleet.db import load_settings_from_db, load_printers_from_db
from printfleet.telegram_bot import send_telegram_message
from printfleet.state import printer_state, state_lock

import socket
import time

START_TIME = time.time()  # ganz oben im Modul setzen


def notify_printfleet_started(version: Optional[str] = None) -> bool:
    """
    Sendet eine Telegram-Nachricht beim Starten von PrintFleet.
    """
    settings = load_settings_from_db()
    chat_id = settings.get("telegram_chat_id")

    if not chat_id:
        return False

    if version:
        text = f"🚀 PrintFleet wurde gestartet (Version {version})."
    else:
        text = "🚀 PrintFleet wurde gestartet."

    return send_telegram_message(chat_id, text)


def _format_printer_status(state_info: Dict[str, Any]) -> str:
    """
    Formatiert den Status aus dem printer_state-Eintrag.
    Erwartet ein Dict mit Feld 'state'.
    """
    if not state_info:
        return "⚪ Noch keine Statusdaten"

    raw_state = (
        state_info.get("state")
        or state_info.get("status")
        or state_info.get("display_state")
        or state_info.get("print_state")
    )

    if not raw_state:
        return f"📄 Rohstatus ohne state-Feld: {state_info}"

    s = str(raw_state).lower()

    # 🔵 aktiv druckend
    if s in ("printing", "busy", "processing"):
        return f"🔵 Druckt ({raw_state})"

    # ⏸️ pausiert
    if s in ("paused", "pausing"):
        return f"⏸️ Pausiert ({raw_state})"

    # 🔴 offline/fehler
    if s in ("offline", "error", "disconnected"):
        return f"🔴 Offline / Fehler ({raw_state})"

    # 🟢 bereit / standby
    if s in ("standby", "idle", "ready"):
        return f"🟢 Bereit ({raw_state})"

    if s in ("no_scanning", "no_monitoring", "no-monitoring"):
        return "⚪ Keine Ueberwachung"

    return f"❓ Unbekannter Status: {raw_state}"


def build_printer_overview_text() -> str:
    """
    Baut den Status-Text für alle Drucker (ohne ihn zu versenden).
    Wird von notify_printer_overview UND vom /status-Command genutzt.
    """
    printers = load_printers_from_db()

    if not printers:
        return "ℹ️ Es sind noch keine Drucker in PrintFleet konfiguriert."

    lines = ["🖨️ Aktuelle Drucker in PrintFleet:"]

    with state_lock:
        for p in printers:
            printer_id = p.get("id")
            name = p.get("name", "Unbenannt")
            backend = p.get("backend", "?")
            host = p.get("host", "?")

            # Mögliche Schlüssel im printer_state testen
            keys_to_try = []
            if printer_id is not None:
                keys_to_try.extend([printer_id, str(printer_id)])
            if host:
                keys_to_try.append(host)
            if name:
                keys_to_try.append(name)

            state_info: Dict[str, Any] = {}
            for key in keys_to_try:
                if key in printer_state:
                    state_info = printer_state.get(key) or {}
                    break

            status_text = _format_printer_status(state_info)
            lines.append(f"• {name} ({backend} @ {host}) – {status_text}")

    return "\n".join(lines)


def notify_printer_overview() -> bool:
    """
    Sendet die Druckerübersicht an die Chat-ID aus den Settings.
    """
    settings = load_settings_from_db()
    chat_id = settings.get("telegram_chat_id")

    if not chat_id:
        return False

    text = build_printer_overview_text()
    return send_telegram_message(chat_id, text)

def build_info_text() -> str:
    settings = load_settings_from_db()
    printers = load_printers_from_db()

    version = PRINTFLEET_VERSION
    hostname = socket.gethostname()

    uptime_s = time.time() - START_TIME
    uptime_h = int(uptime_s // 3600)
    uptime_m = int((uptime_s % 3600) // 60)

    total = len(printers)
    num_octoprint = sum(1 for p in printers if p.get("backend") == "octoprint")
    num_moonraker = sum(1 for p in printers if p.get("backend") == "moonraker")

    lines = [
        "ℹ️ PrintFleet Info",
        f"• Version: {version}",
        f"• Uptime: {uptime_h}h {uptime_m}min",
        f"• Drucker insgesamt: {total}",
        f"  - OctoPrint: {num_octoprint}",
        f"  - Moonraker: {num_moonraker}",
        f"• Server: {hostname}",
        "",
        "Verfügbare Commands:",
        "• /status – aktueller Druckerstatus",
        "• /info – Systeminfo zu PrintFleet",
    ]
    return "\n".join(lines)
