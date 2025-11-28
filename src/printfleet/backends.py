#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import Optional, Any, Dict
from typing import Tuple
from urllib.parse import urlparse
import time
import requests

import json
import websocket  # aus dem Paket websocket-client


def _num(x: Any) -> float:
    """Hilfsfunktion: versucht, x als float zu interpretieren, sonst 0.0."""
    try:
        return float(x)
    except Exception:
        return 0.0



def fetch_centauri(base_url: str, timeout: float = 5.0) -> Tuple[
    str, str, float, float, float, float, float, float
]:
    """
    Elegoo Centurio / Centauri Carbon Backend (SDCP über WebSocket).

    Laut OpenCentauri-Doku:
      - WebSocket-Port: 3030
      - Mögliche Pfade:
          /websocket, /ws, /, /api/websocket, /sdcp
      - Nachrichten-Format: JSON mit "Status" / "PrintInfo" etc.
    """

    parsed = urlparse(base_url)
    host = parsed.hostname or ""
    if not host:
        raise RuntimeError(f"Ungültige base_url für Centauri: {base_url!r}")

    ws_paths = ["/websocket", "/ws", "/", "/api/websocket", "/sdcp"]

    last_error: Optional[Exception] = None

    for path in ws_paths:
        ws_url = f"ws://{host}:3030{path}"

        try:
            ws = websocket.create_connection(ws_url, timeout=timeout)
        except Exception as e:
            last_error = e
            continue

        try:
            # Optionales Ping, manche Geräte senden erst dann Status
            try:
                ws.send("ping")
            except Exception:
                pass

            data = None
            deadline = time.time() + timeout

            # Mehrere Nachrichten lesen, bis eine Status-Message kommt
            while time.time() < deadline:
                try:
                    raw_msg = ws.recv()
                except Exception as e:
                    last_error = e
                    data = None
                    break

                # JSON versuchen
                try:
                    obj = json.loads(raw_msg)
                except Exception:
                    continue

                # Status gefunden?
                if isinstance(obj, dict) and "Status" in obj:
                    data = obj
                    break

            if data is None:
                if last_error is None:
                    last_error = RuntimeError(f"Keine Status-Message über SDCP auf Pfad {path}")
                continue

            # Ab hier haben wir gültige Daten
            status = data.get("Status", {}) or {}
            pi = status.get("PrintInfo", {}) or {}

            hotend = float(status.get("TempOfNozzle", 0.0))
            hotend_t = float(status.get("TempTargetNozzle", 0.0))
            bed = float(status.get("TempOfHotbed", 0.0))
            bed_t = float(status.get("TempTargetHotbed", 0.0))

            elapsed = float(pi.get("CurrentTicks", 0.0))
            total = float(pi.get("TotalTicks", 0.0)) or 0.0

            prog_raw = float(pi.get("Progress", 0.0))
            if prog_raw > 1.0:
                progress = prog_raw / 100.0
            elif 0.0 < prog_raw <= 1.0:
                progress = prog_raw
            elif total > 0.0:
                progress = max(0.0, min(1.0, elapsed / total))
            else:
                progress = 0.0

            filename = pi.get("Filename", "") or ""

            st_raw = int(pi.get("Status", 0))
            state_map = {
                0: "standby",
                1: "printing",
                2: "paused",
                3: "stopped",
                4: "complete",
            }
            state = state_map.get(st_raw, "standby")

            return state, filename, elapsed, progress, hotend, hotend_t, bed, bed_t

        finally:
            try:
                ws.close()
            except Exception:
                pass

    if last_error:
        raise RuntimeError(f"SDCP-Status konnte nicht gelesen werden: {last_error}")
    else:
        raise RuntimeError("SDCP-Status konnte nicht gelesen werden (unbekannter Fehler)")


def fetch_moonraker(base_url: str, token: Optional[str], timeout: float):
    """Statusdaten von einem Moonraker-Backend abholen."""

    path = (
        "/printer/objects/query?"
        "print_stats=state,filename,print_duration"
        "&virtual_sdcard=progress"
        "&extruder=temperature,target"
        "&heater_bed=temperature,target"
    )
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    r = requests.get(base_url + path, headers=headers, timeout=timeout)
    r.raise_for_status()
    data = r.json().get("result", {}).get("status", {})

    ps = data.get("print_stats", {}) or {}
    vsd = data.get("virtual_sdcard", {}) or {}
    ext = data.get("extruder", {}) or {}
    bed = data.get("heater_bed", {}) or {}

    state = ps.get("state", "unknown")
    filename = ps.get("filename", "") or ""
    elapsed = _num(ps.get("print_duration", 0.0))
    progress = _num(vsd.get("progress", 0.0))

    hotend = _num(ext.get("temperature"))
    hotend_t = _num(ext.get("target"))
    bed_c = _num(bed.get("temperature"))
    bed_t = _num(bed.get("target"))
    return (state, filename, elapsed, progress, hotend, hotend_t, bed_c, bed_t)


def fetch_octoprint(base_url: str, api_key: str, timeout: float):
    """Statusdaten von einem OctoPrint-Backend abholen."""

    headers = {"X-Api-Key": api_key}
    r_job = requests.get(base_url + "/api/job", headers=headers, timeout=timeout)
    r_job.raise_for_status()
    job = r_job.json()

    r_prn = requests.get(base_url + "/api/printer", headers=headers, timeout=timeout)
    r_prn.raise_for_status()
    prn = r_prn.json()

    state_text = job.get("state") or ""
    progress = (job.get("progress", {}) or {}).get("completion")
    progress01 = (progress / 100.0) if isinstance(progress, (int, float)) else 0.0
    elapsed = _num((job.get("progress", {}) or {}).get("printTime"))
    filename = ""
    try:
        filename = job.get("job", {}).get("file", {}).get("name") or ""
    except Exception:
        pass

    tool0 = (prn.get("temperature", {}) or {}).get("tool0", {}) or {}
    bed = (prn.get("temperature", {}) or {}).get("bed", {}) or {}
    hotend = _num(tool0.get("actual"))
    hotend_t = _num(tool0.get("target"))
    bed_c = _num(bed.get("actual"))
    bed_t = _num(bed.get("target"))

    st = state_text.lower()
    if "printing" in st or "in progress" in st:
        state = "printing"
    elif "paused" in st:
        state = "paused"
    elif "cancelling" in st or "cancelled" in st:
        state = "cancelled"
    elif any(k in st for k in ("complete", "finished", "done")):
        state = "complete"
    elif any(k in st for k in ("error", "offline", "closed")):
        state = "error"
    else:
        state = "standby"

    return (state, filename, elapsed, progress01, hotend, hotend_t, bed_c, bed_t)