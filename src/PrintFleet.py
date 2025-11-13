#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time, sys, threading, requests
from typing import Optional, Tuple, Dict, Any
from flask import Flask, jsonify, Response

# ---- Konfiguration laden ----
try:
    from PrintFleetPrinterList import PRINTERS, GLOBAL
except ImportError:
    try:
        from PrintFleetPrinterList import PRINTERS
        GLOBAL = {}
    except Exception as e:
        print("Konfigurationsdatei 'dashboardPrinterList.py' fehlt/fehlerhaft.", file=sys.stderr)
        raise

app = Flask(__name__)
state_lock = threading.Lock()
printer_state: Dict[str, Dict[str, Any]] = {}

# ----------------- Helfer -----------------
def fmt_hms(seconds: float) -> str:
    s = int(seconds or 0)
    h, m, s2 = s // 3600, (s % 3600) // 60, s % 60
    return f"{h}:{m:02d}:{s2:02d} h" if h > 0 else f"{m:02d}:{s2:02d} min"

def progress_bar_pct(progress: float) -> float:
    return round(max(0.0, min(1.0, float(progress or 0.0))) * 100.0, 1)

def _num(x):
    try:
        return float(x)
    except Exception:
        return 0.0

# ----------------- Backends -----------------
def fetch_moonraker(base_url: str, token: Optional[str], timeout: float):
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

    ps  = data.get("print_stats", {}) or {}
    vsd = data.get("virtual_sdcard", {}) or {}
    ext = data.get("extruder", {}) or {}
    bed = data.get("heater_bed", {}) or {}

    state    = ps.get("state", "unknown")
    filename = ps.get("filename", "") or ""
    elapsed  = _num(ps.get("print_duration", 0.0))
    progress = _num(vsd.get("progress", 0.0))

    hotend   = _num(ext.get("temperature"))
    hotend_t = _num(ext.get("target"))
    bed_c    = _num(bed.get("temperature"))
    bed_t    = _num(bed.get("target"))
    return (state, filename, elapsed, progress, hotend, hotend_t, bed_c, bed_t)

def fetch_octoprint(base_url: str, api_key: str, timeout: float):
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
    bed   = (prn.get("temperature", {}) or {}).get("bed", {}) or {}
    hotend   = _num(tool0.get("actual"))
    hotend_t = _num(tool0.get("target"))
    bed_c    = _num(bed.get("actual"))
    bed_t    = _num(bed.get("target"))

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

# ----------------- Monitor-Thread -----------------
def monitor_printer(prn: dict, global_defaults: dict, stop_evt: threading.Event):
    name   = prn.get("name", prn.get("host", "UNNAMED"))
    host   = prn["host"]
    port   = prn.get("port", global_defaults.get("port", 80))
    https  = prn.get("https", global_defaults.get("https", False))
    be     = (prn.get("backend") or "moonraker").lower()
    token  = prn.get("token")
    api_key= prn.get("api_key")
    interval = float(prn.get("interval", global_defaults.get("interval", 5.0)))
    err_interval = float(prn.get("error_report_interval", global_defaults.get("error_report_interval", 30.0)))

    scheme = "https" if https else "http"
    base_url = f"{scheme}://{host}:{port}"

    consecutive_errors = 0
    last_error_report_ts = 0.0
    last_error_text = None

    while not stop_evt.is_set():
        try:
            if be == "octoprint":
                res = fetch_octoprint(base_url, api_key=api_key, timeout=max(5.0, interval+2.0))
            else:
                res = fetch_moonraker(base_url, token=token, timeout=max(5.0, interval+2.0))

            (state, filename, elapsed, progress,
             hotend, hotend_t, bed, bed_t) = res

            eta_s = 0.0
            if progress and progress > 0 and elapsed and elapsed > 0:
                eta_s = elapsed * (1.0/progress - 1.0)

            with state_lock:
                printer_state[name] = {
                    "name": name, "backend": be, "host": host,
                    "state": state, "filename": filename,
                    "progress_pct": progress_bar_pct(progress),
                    "elapsed_s": float(elapsed), "eta_s": float(eta_s),
                    "elapsed_hms": fmt_hms(elapsed), "eta_hms": fmt_hms(eta_s),
                    "hotend": round(hotend,1), "hotend_t": round(hotend_t,1),
                    "bed": round(bed,1), "bed_t": round(bed_t,1),
                    "last_update": int(time.time()), "error": None,
                    "link": f"{scheme}://{host}:{port}/"
                }

            consecutive_errors = 0
            last_error_text = None
            last_error_report_ts = 0.0

        except requests.exceptions.RequestException as e:
            consecutive_errors += 1
            err = f"NICHT ERREICHBAR (Versuch {consecutive_errors}): {e}"
            now = time.time()
            with state_lock:
                st = printer_state.get(name, {"name": name, "backend": be, "host": host})
                st.update({
                    "state": "offline", "filename": "",
                    "progress_pct": 0.0, "elapsed_s": 0.0, "eta_s": 0.0,
                    "elapsed_hms": "00:00 min", "eta_hms": "00:00 min",
                    "hotend": 0.0, "hotend_t": 0.0, "bed": 0.0, "bed_t": 0.0,
                    "last_update": int(now), "error": err,
                    "link": f"{scheme}://{host}:{port}/"
                })
                printer_state[name] = st

            if (consecutive_errors == 1) or (err != last_error_text) or (now - last_error_report_ts >= err_interval):
                print(f"[{name}] {err}", file=sys.stderr)
                last_error_text = err
                last_error_report_ts = now

        except Exception as e:
            consecutive_errors += 1
            err = f"Unerwarteter Fehler: {e}"
            now = time.time()
            with state_lock:
                st = printer_state.get(name, {"name": name, "backend": be, "host": host})
                st.update({
                    "state": "error", "filename": "",
                    "progress_pct": 0.0, "elapsed_s": 0.0, "eta_s": 0.0,
                    "elapsed_hms": "00:00 min", "eta_hms": "00:00 min",
                    "hotend": 0.0, "hotend_t": 0.0, "bed": 0.0, "bed_t": 0.0,
                    "last_update": int(now), "error": err,
                    "link": f"{scheme}://{host}:{port}/"
                })
                printer_state[name] = st

            if (consecutive_errors == 1) or (err != last_error_text) or (now - last_error_report_ts >= err_interval):
                print(f"[{name}] {err}", file=sys.stderr)
                last_error_text = err
                last_error_report_ts = now

        time.sleep(max(0.2, interval))

# ----------------- Flask Endpoints -----------------
@app.route("/")
def index() -> Response:
    html = """
<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8">
<title>Drucker-Status</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="stylesheet" href="/static/DashboardStyle.css">
</head>
<body>
  <h1>Drucker-Status</h1>
  <p><small class="mono">Aktualisierung alle 5&nbsp;Sekunden</small></p>
  <table id="tbl">
    <thead>
      <tr>
        <th>Name</th>
        <th>Backend</th>
        <th>Status</th>
        <th>Datei</th>
        <th style="min-width:160px">Fortschritt</th>
        <th>verstrichen</th>
        <th>Rest</th>
        <th>Hotend (Ist/Target)</th>
        <th>Bed (Ist/Target)</th>
        <th>Zuletzt</th>
        <th>Aktionen</th>
        <th>Fehler</th>
      </tr>
    </thead>
    <tbody></tbody>
  </table>

<script>
function pctColor(p){
  if(p >= 80) return 'linear-gradient(90deg,#16a34a,#22c55e)'; // grün
  if(p >= 40) return 'linear-gradient(90deg,#ca8a04,#eab308)'; // gelb
  return 'linear-gradient(90deg,#dc2626,#ef4444)';             // rot
}
function toFixed1(x){
  return (typeof x === 'number' && isFinite(x)) ? x.toFixed(1) : (x ?? '');
}
async function loadData(){
  try{
    const r = await fetch('/api/status', {cache:'no-store'});
    const data = await r.json();
    const tbody = document.querySelector('#tbl tbody');
    tbody.innerHTML = '';
    const now = Math.floor(Date.now()/1000);

    (data || []).forEach(p => {
      // Fallbacks
      const name = p.name || '';
      const backend = p.backend || '';
      const state = p.state || 'standby';
      const filename = p.filename || '';
      const progress_pct = (typeof p.progress_pct === 'number' && isFinite(p.progress_pct)) ? p.progress_pct : 0;
      const elapsed_hms = p.elapsed_hms || '';
      const eta_hms = p.eta_hms || '';
      const hotend = (typeof p.hotend === 'number') ? p.hotend : 0;
      const hotend_t = (typeof p.hotend_t === 'number') ? p.hotend_t : 0;
      const bed = (typeof p.bed === 'number') ? p.bed : 0;
      const bed_t = (typeof p.bed_t === 'number') ? p.bed_t : 0;
      const last_update = (typeof p.last_update === 'number') ? p.last_update : 0;
      const error = p.error || '';
      const link = p.link || '';

      const tr = document.createElement('tr');
      tr.className = state;

      const td = (t)=>{ const x=document.createElement('td'); x.textContent=t; return x; };
      const tdHTML = (h)=>{ const x=document.createElement('td'); x.innerHTML=h; return x; };

      const badge = '<span class="badge ' + state + '">' + state + '</span>';

      // Fortschrittsbalken
      const progCell = document.createElement('td');
      const progWrap = document.createElement('div');
      progWrap.className = 'progress';
      const inner = document.createElement('div');
      inner.style.width = progress_pct + '%';
      inner.style.background = pctColor(progress_pct);
      progWrap.appendChild(inner);
      const label = document.createElement('div');
      label.style.fontSize='12px'; label.style.marginTop='4px';
      label.textContent = (isFinite(progress_pct) ? progress_pct.toFixed(1) : '0.0') + '%';
      progCell.appendChild(progWrap);
      progCell.appendChild(label);

      // Aktionen
      const actions = document.createElement('td'); actions.className='actions';
      if(link){
        const a1 = document.createElement('a'); a1.href = link; a1.target = '_blank'; a1.className='btn';
        a1.textContent = 'Web-UI öffnen';
        actions.appendChild(a1);
      }

      const last = last_update ? (now - last_update) : 0;
      const lastTxt = (last >= 0) ? (last + ' s') : '';

      tr.appendChild(td(name));
      tr.appendChild(td(backend));
      tr.appendChild(tdHTML(badge));
      tr.appendChild(td(filename));
      tr.appendChild(progCell);
      tr.appendChild(td(elapsed_hms));
      tr.appendChild(td(eta_hms));
      tr.appendChild(td(toFixed1(hotend) + ' / ' + toFixed1(hotend_t) + ' °C'));
      tr.appendChild(td(toFixed1(bed)    + ' / ' + toFixed1(bed_t)    + ' °C'));
      tr.appendChild(td(lastTxt));
      tr.appendChild(actions);
      tr.appendChild(td(error));

      tbody.appendChild(tr);
    });
  } catch(e){
    console.error('fetch error', e);
  }
}
loadData();
setInterval(loadData, 5000);
</script>
</body>
</html>
"""
    return Response(html, mimetype="text/html")


@app.route("/api/status")
def api_status():
    with state_lock:
        rows = [printer_state[k] for k in sorted(printer_state.keys())]
    return jsonify(rows)

# ----------------- Start Threads + App -----------------
def start_threads():
    stop_evt = threading.Event()
    threads = []
    for prn in PRINTERS:
        t = threading.Thread(target=monitor_printer,
                             args=(prn, GLOBAL if isinstance(GLOBAL, dict) else {}, stop_evt),
                             daemon=True)
        t.start()
        threads.append(t)
    return stop_evt, threads

if __name__ == "__main__":
    # Initiale Platzhalter
    with state_lock:
        for prn in PRINTERS:
            name = prn.get("name", prn.get("host", "UNNAMED"))
            host = prn["host"]
            port = prn.get("port", GLOBAL.get("port", 80))
            https = prn.get("https", GLOBAL.get("https", False))
            scheme = "https" if https else "http"
            printer_state[name] = {
                "name": name, "backend": prn.get("backend","moonraker"),
                "host": host, "state": "standby", "filename": "",
                "progress_pct": 0.0, "elapsed_s": 0.0, "eta_s": 0.0,
                "elapsed_hms": "00:00 min", "eta_hms": "00:00 min",
                "hotend": 0.0, "hotend_t": 0.0, "bed": 0.0, "bed_t": 0.0,
                "last_update": int(time.time()), "error": None,
                "link": f"{scheme}://{host}:{port}/"
            }

    stop_evt, threads = start_threads()
    try:
        app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
    finally:
        stop_evt.set()
        for t in threads:
            t.join(timeout=2.0)