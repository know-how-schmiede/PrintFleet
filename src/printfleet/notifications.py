#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import Optional, Dict, Any

from printfleet.db import load_settings_from_db, load_printers_from_db
from printfleet.telegram_bot import send_telegram_message
from printfleet.state import printer_state, state_lock


def notify_printfleet_started(version: Optional[str] = None) -> bool:
    """
    Sendet eine Telegram-Nachricht beim Starten von PrintFleet.
    Nutzt die telegram_chat_id aus der Settings-Tabelle.
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
    Erwartet ein Dict wie:
    {
        "id": ...,
        "name": ...,
        "state": "offline" | "standby" | "printing" | ...
        ...
    }
    """
    if not state_info:
        return "⚪ Noch keine Statusdaten"

    # Die eigentliche Status-Quelle – so wie in deinem Beispiel:
    # 'state': 'offline' / 'standby' / 'printing' ...
    raw_state = (
        state_info.get("state")
        or state_info.get("status")
        or state_info.get("display_state")
        or state_info.get("print_state")
    )

    if not raw_state:
        return f"📄 Rohstatus ohne state-Feld: {state_info}"

    s = str(raw_state).lower()

    # 🔵 Aktiver Druck
    if s in ("printing", "busy", "processing"):
        return f"🔵 Druckt ({raw_state})"

    # ⏸️ Pause
    if s in ("paused", "pausing"):
        return f"⏸️ Pausiert ({raw_state})"

    # 🔴 Offline / Fehler
    if s in ("offline", "error", "disconnected"):
        return f"🔴 Offline / Fehler ({raw_state})"

    # 🟢 Bereit / Standby
    if s in ("standby", "idle", "ready"):
        return f"🟢 Bereit ({raw_state})"

    # Fallback
    return f"❓ Unbekannter Status: {raw_state}"



def notify_printer_overview() -> bool:
    """
    Sendet eine Übersicht der aktuell in PrintFleet konfigurierten Drucker
    inkl. Status per Telegram.
    """
    settings = load_settings_from_db()
    chat_id = settings.get("telegram_chat_id")

    if not chat_id:
        return False

    printers = load_printers_from_db()

    if not printers:
        text = "ℹ️ PrintFleet wurde gestartet, aber es sind noch keine Drucker konfiguriert."
        return send_telegram_message(chat_id, text)

    lines = ["🖨️ Aktuelle Drucker in PrintFleet:"]

    with state_lock:
        for p in printers:
            printer_id = p.get("id")
            name = p.get("name", "Unbenannt")
            backend = p.get("backend", "?")
            host = p.get("host", "?")

            # Mögliche Schlüssel, unter denen der Drucker im printer_state liegen könnte
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

    text = "\n".join(lines)
    return send_telegram_message(chat_id, text)