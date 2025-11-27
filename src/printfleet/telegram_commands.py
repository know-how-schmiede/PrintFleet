#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import time
import requests
from typing import Optional

from printfleet.notifications import build_printer_overview_text, build_info_text
from printfleet.db import load_settings_from_db
from printfleet.telegram_bot import send_telegram_message

def _handle_info_command(chat_id: int):
    text = build_info_text()
    send_telegram_message(chat_id, text)

def _get_bot_token() -> Optional[str]:
    return os.getenv("PRINTFLEET_TELEGRAM_TOKEN")


def _get_updates(token: str, offset: Optional[int] = None, timeout: int = 25):
    url = f"https://api.telegram.org/bot{token}/getUpdates"
    params = {
        "timeout": timeout,
        "allowed_updates": ["message"],
    }
    if offset is not None:
        params["offset"] = offset
    resp = requests.get(url, params=params, timeout=timeout + 5)
    resp.raise_for_status()
    data = resp.json()
    if not data.get("ok", False):
        return []
    return data.get("result", [])


def _handle_status_command(chat_id: int):
    """
    Wird aufgerufen, wenn der Bot eine /status-Nachricht erhält.
    Baut den Status-Text und sendet ihn an den Chat.
    """
    text = build_printer_overview_text()
    send_telegram_message(chat_id, text)


def telegram_command_loop(stop_evt):
    """
    Pollt die Telegram-API regelmäßig (getUpdates) und reagiert auf /status.
    stop_evt ist das gleiche Event, das du schon für die anderen Threads verwendest.
    """
    token = _get_bot_token()
    if not token:
        print("Telegram: Kein Token gesetzt, Command-Loop wird nicht gestartet.")
        return

    print("Telegram: Command-Loop gestartet (/status).")

    last_update_id: Optional[int] = None

    # Optional: Standard-Chat aus Settings, falls du später andere Commands brauchst
    settings = load_settings_from_db()
    default_chat_id = settings.get("telegram_chat_id")

    while not stop_evt.is_set():
        try:
            updates = _get_updates(token, offset=last_update_id + 1 if last_update_id is not None else None)

            for upd in updates:
                last_update_id = upd.get("update_id", last_update_id)

                msg = upd.get("message") or {}
                text = msg.get("text") or ""
                chat = msg.get("chat") or {}
                chat_id = chat.get("id")

                if not text or chat_id is None:
                    continue

                t = text.strip()
                # /status oder /status@DeinBotName
                if t == "/status" or t.startswith("/status@"):
                    _handle_status_command(chat_id)
                elif t == "/info" or t.startswith("/info@"):
                    _handle_info_command(chat_id)

        except Exception as e:
            print(f"Telegram: Fehler im Command-Loop: {e}")
            time.sleep(5.0)
            continue

    print("Telegram: Command-Loop beendet.")
