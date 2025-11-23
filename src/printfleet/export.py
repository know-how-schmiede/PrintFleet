# src/printfleet/export.py
import time
import io
import json

from flask import Blueprint, send_file, request, redirect, url_for
from printfleet.i18n import _

from printfleet.db import (
    load_settings_from_db,
    load_printers_from_db,
    get_db_connection,
)

bp = Blueprint("export", __name__)


# -------------------------------------------------
# Export-Helfer
# -------------------------------------------------

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


from flask import flash

@bp.route("/export/printers", methods=["GET"])
def export_printers():
    json_bytes = make_export_payload("printers")
    buf = io.BytesIO(json_bytes)
    buf.seek(0)

    timestamp = time.strftime("%Y%m%d-%H%M%S")
    filename = f"PrintFleet_printers_{timestamp}.json"

    flash(_("msg_export_printers_success"), "success")

    return send_file(
        buf,
        mimetype="application/json",
        as_attachment=True,
        download_name=filename,
    )



@bp.route("/export/settings", methods=["GET"])
def export_settings():
    json_bytes = make_export_payload("settings")
    buf = io.BytesIO(json_bytes)
    buf.seek(0)

    timestamp = time.strftime("%Y%m%d-%H%M%S")
    filename = f"PrintFleet_settings_{timestamp}.json"

    flash(_("msg_export_settings_success"), "success")

    return send_file(
        buf,
        mimetype="application/json",
        as_attachment=True,
        download_name=filename,
    )



# -------------------------------------------------
# Import-Funktionen (Backup wieder einspielen)
# -------------------------------------------------

def _insert_items_into_table(table: str, items: list[dict]) -> None:
    """
    Generische Helper-Funktion:
    - löscht alle Einträge in 'table'
    - fügt items (Liste von Dicts) wieder ein
    Die Keys der Dicts müssen den Spaltennamen der Tabelle entsprechen.
    """
    db = get_db_connection()
    try:
        db.execute(f"DELETE FROM {table}")
        for item in items:
            if not isinstance(item, dict):
                continue
            columns = list(item.keys())
            if not columns:
                continue
            col_names = ", ".join(columns)
            placeholders = ", ".join(["?"] * len(columns))
            values = [item[col] for col in columns]
            db.execute(
                f"INSERT INTO {table} ({col_names}) VALUES ({placeholders})",
                values,
            )
        db.commit()
    except Exception:
        db.rollback()
        raise


@bp.route("/import/printers", methods=["POST"])
def import_printers():
    file = request.files.get("file")
    if not file or file.filename == "":
        flash(_("msg_import_no_file"), "error")
        return redirect(url_for("printers.printer_list"))

    try:
        data = json.load(file.stream)
    except json.JSONDecodeError:
        flash(_("msg_import_invalid_json"), "error")
        return redirect(url_for("printers.printer_list"))

    if data.get("export_type") != "printers":
        flash(_("msg_import_wrong_type_printers"), "error")
        return redirect(url_for("printers.printer_list"))

    items = data.get("items")
    if not isinstance(items, list):
        flash(_("msg_import_invalid_structure"), "error")
        return redirect(url_for("printers.printer_list"))

    _insert_items_into_table("printers", items)

    flash(_("msg_import_printers_success"), "success")
    return redirect(url_for("printers.printer_list"))



@bp.route("/import/settings", methods=["POST"])
def import_settings():
    file = request.files.get("file")
    if not file or file.filename == "":
        flash(_("msg_import_no_file"), "error")
        return redirect(url_for("settings.settings_page"))

    try:
        data = json.load(file.stream)
    except json.JSONDecodeError:
        flash(_("msg_import_invalid_json"), "error")
        return redirect(url_for("settings.settings_page"))

    if data.get("export_type") != "settings":
        flash(_("msg_import_wrong_type_settings"), "error")
        return redirect(url_for("settings.settings_page"))

    items = data.get("items")
    if not isinstance(items, list) or not items:
        flash(_("msg_import_invalid_structure"), "error")
        return redirect(url_for("settings.settings_page"))

    _insert_items_into_table("settings", [items[0]])

    flash(_("msg_import_settings_success"), "success")
    return redirect(url_for("settings.settings_page"))