#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import Optional, Any, Dict

import requests


def _num(x: Any) -> float:
    """Hilfsfunktion: versucht, x als float zu interpretieren, sonst 0.0."""
    try:
        return float(x)
    except Exception:
        return 0.0


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