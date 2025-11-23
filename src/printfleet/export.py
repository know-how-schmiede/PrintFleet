# src/printfleet/export.py
import time
import io
import json
from flask import Blueprint, send_file

from printfleet.db import load_settings_from_db, load_printers_from_db

bp = Blueprint("export", __name__)

def make_export_payload(export_type: str) -> bytes:
    """
    Erzeugt ein JSON-Backup für 'printers' oder 'settings' und liefert die Bytes.
    Struktur:
    {
        "export_type": "printers" | "settings",
        "exported_at": "YYYY-MM-DDTHH:MM:SS",
        "items": [ ... ]
    }
    """
    if export_type == "printers":
        items = load_printers_from_db()
    elif export_type == "settings":
        settings = load_settings_from_db() or {}
        items = [settings]
    else:
        raise ValueError(f"Unsupported export_type: {export_type}")

    data = {
        "export_type": export_type,
        "exported_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "items": items,
    }
    return json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")


@bp.route("/export/printers", methods=["GET"])
def export_printers():
    """Exportiert alle Drucker als JSON-Backup."""
    json_bytes = make_export_payload("printers")
    buf = io.BytesIO(json_bytes)
    buf.seek(0)

    timestamp = time.strftime("%Y%m%d-%H%M%S")
    filename = f"PrintFleet_printers_{timestamp}.json"

    return send_file(
        buf,
        mimetype="application/json",
        as_attachment=True,
        download_name=filename,
    )


@bp.route("/export/settings", methods=["GET"])
def export_settings():
    """Exportiert die Settings als JSON-Backup."""
    json_bytes = make_export_payload("settings")
    buf = io.BytesIO(json_bytes)
    buf.seek(0)

    timestamp = time.strftime("%Y%m%d-%H%M%S")
    filename = f"PrintFleet_settings_{timestamp}.json"

    return send_file(
        buf,
        mimetype="application/json",
        as_attachment=True,
        download_name=filename,
    )