# src/printfleet/telegram_bot.py
import os
import logging
from typing import Optional

import requests


# Basis-URL für die Telegram Bot API
def _get_bot_token() -> Optional[str]:
    """
    Liest den Bot-Token aus der Environment-Variable PRINTFLEET_TELEGRAM_TOKEN.
    Gibt None zurück, wenn nichts gesetzt ist.
    """
    return os.getenv("PRINTFLEET_TELEGRAM_TOKEN")


def send_telegram_message(chat_id: str, text: str) -> bool:
    """
    Sendet eine einfache Text-Nachricht an einen Telegram-Chat.
    Rückgabe: True bei Erfolg, False bei Fehler.
    Diese Funktion ist bewusst klein gehalten, damit sie später
    leicht erweitert werden kann (ParseMode, Keyboards, etc.).
    """
    token = _get_bot_token()
    if not token:
        logging.warning("Telegram: Kein Bot-Token gesetzt (PRINTFLEET_TELEGRAM_TOKEN).")
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"

    payload = {
        "chat_id": chat_id,
        "text": text,
        # später z.B. "parse_mode": "Markdown" oder "HTML"
    }

    try:
        resp = requests.post(url, json=payload, timeout=5)
        if resp.status_code != 200:
            logging.warning("Telegram: Fehler %s – Antwort: %s",
                            resp.status_code, resp.text)
            return False

        data = resp.json()
        if not data.get("ok", False):
            logging.warning("Telegram: API-Fehler: %s", data)
            return False

        return True

    except Exception as e:
        logging.exception("Telegram: Exception beim Senden der Nachricht: %s", e)
        return False