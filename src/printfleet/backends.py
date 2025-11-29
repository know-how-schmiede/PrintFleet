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

    Strategie:
      - Aus base_url Host extrahieren
      - WebSocket zu ws://<host>:3030/websocket
      - 'ping' senden
      - genau EINE Status-Message empfangen
      - Verbindung schließen
      - State anhand von PrintInfo.Status UND Progress/Elapsed heuristisch bestimmen
    """

    parsed = urlparse(base_url)
    host = parsed.hostname or ""
    if not host:
        raise RuntimeError(f"Ungültige base_url für Centauri: {base_url!r}")

    ws_url = f"ws://{host}:3030/websocket"

    # WebSocket verbinden
    ws = websocket.create_connection(ws_url, timeout=timeout)

    try:
        # Ping schicken – wie im Testscript
        try:
            ws.send("ping")
        except Exception:
            # Wenn das schiefgeht, versuchen wir trotzdem zu lesen
            pass

        # Eine Nachricht lesen
        ws.settimeout(timeout)
        raw_msg = ws.recv()

        # JSON parsen
        data = json.loads(raw_msg)

        status = data.get("Status")
        if not isinstance(status, dict):
            raise RuntimeError("Keine gültigen Status-Daten im SDCP-Response")

        pi = status.get("PrintInfo", {}) or {}

        # Temperaturen
        hotend = float(status.get("TempOfNozzle", 0.0))
        hotend_t = float(status.get("TempTargetNozzle", 0.0))
        bed = float(status.get("TempOfHotbed", 0.0))
        bed_t = float(status.get("TempTargetHotbed", 0.0))

        # Zeit
        elapsed = float(pi.get("CurrentTicks", 0.0))
        total = float(pi.get("TotalTicks", 0.0)) or 0.0

        # Fortschritt-Rohwert und normiert 0..1
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

        # Roh-Status aus PrintInfo.Status (Elegoo nutzt hier offenbar 0 sehr häufig)
        st_raw = int(pi.get("Status", 0))
        state_map = {
            0: "standby",
            1: "printing",
            2: "paused",
            3: "stopped",
            4: "complete",
        }
        state = state_map.get(st_raw, "standby")

        # --- Heuristik: Status aus Progress/Elapsed ableiten ---

        # Wenn Fortschritt > 0 und < 1: wir drucken
        if 0.0 < progress < 1.0:
            state = "printing"

        # Falls Progress >= 1 (oder total/elapsed gleichgezogen): Druck fertig
        if progress >= 1.0 or (total > 0.0 and elapsed >= total):
            state = "complete"

        # Falls bereits Zeit/Layer laufen, aber Progress noch 0:
        if state == "standby" and filename and (elapsed > 0.0 or prog_raw > 0.0):
            state = "printing"

        return state, filename, elapsed, progress, hotend, hotend_t, bed, bed_t

    finally:
        try:
            ws.close()
        except Exception:
            pass





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