# src/printfleet/debug/telegram_test.py

from flask import jsonify

from . import bp  # <-- den bestehenden debug-Blueprint benutzen!
from printfleet.db import load_settings_from_db
from printfleet.telegram_bot import send_telegram_message


def send_telegram_test_message() -> bool:
    """
    Liest die Telegram-Chat-ID aus den Settings (id=1) und sendet eine Testnachricht.
    """
    settings = load_settings_from_db()
    chat_id = settings.get("telegram_chat_id")

    if not chat_id:
        return False

    text = "👋 Hallo von PrintFleet! Die Telegram-Anbindung funktioniert."
    return send_telegram_message(chat_id, text)


@bp.route("/debug/telegram_test")
def test_route():
    """HTTP-Test über Browser."""
    ok = send_telegram_test_message()

    if ok:
        return jsonify({"ok": True, "message": "Telegram Test gesendet"})
    else:
        return jsonify({"ok": False, "error": "Telegram Sendefehler"}), 500