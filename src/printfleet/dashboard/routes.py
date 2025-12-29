#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import shutil
import subprocess
from urllib.parse import quote

from flask import Response, render_template, jsonify, stream_with_context

from printfleet.db import load_settings_from_db
from printfleet.state import state_lock, printer_state
from . import bp


def _sorted_printer_rows():
    with state_lock:
        return [printer_state[k] for k in sorted(printer_state.keys())]


def _build_rtsp_url(host: str, user: str, password: str) -> str:
    if not host or not user or not password:
        return ""
    safe_user = quote(user, safe="")
    safe_password = quote(password, safe="")
    return f"rtsp://{safe_user}:{safe_password}@{host}:554/stream1"


@bp.route("/")
def index() -> str:
    # 'page' wird im Template benutzt, um den aktiven Menüpunkt zu markieren
    return render_template("index.html", page="overview")


@bp.route("/api/status")
def api_status():
    return jsonify(_sorted_printer_rows())


@bp.route("/kiosk")
def kiosk() -> str:
    settings = load_settings_from_db()
    kiosk_streams = []
    for idx in range(1, 5):
        stream_url = settings.get(f"kiosk_stream_url_{idx}") or ""
        stream_is_rtsp = stream_url.lower().startswith("rtsp://")
        cam_host = settings.get(f"kiosk_camera_host_{idx}") or ""
        cam_user = settings.get(f"kiosk_camera_user_{idx}") or ""
        cam_password = settings.get(f"kiosk_camera_password_{idx}") or ""
        show_iframe = bool(stream_url and not stream_is_rtsp)
        show_mjpeg = stream_is_rtsp or (cam_host and cam_user and cam_password)

        kiosk_streams.append(
            {
                "index": idx,
                "iframe_url": stream_url if show_iframe else "",
                "show_iframe": show_iframe,
                "show_mjpeg": show_mjpeg,
            }
        )
    return render_template(
        "kiosk.html",
        page="kiosk",
        kiosk_streams=kiosk_streams,
        kiosk_layout=settings.get("kiosk_stream_layout") or "standard",
    )


@bp.route("/api/kiosk/status")
def kiosk_status():
    return jsonify(_sorted_printer_rows())


@bp.route("/kiosk/stream.mjpg")
@bp.route("/kiosk/stream/<int:stream_id>.mjpg")
def kiosk_stream(stream_id: int = 1):
    if stream_id < 1 or stream_id > 4:
        return ("", 404)
    settings = load_settings_from_db()
    stream_url = settings.get(f"kiosk_stream_url_{stream_id}") or ""
    if stream_url.lower().startswith("rtsp://"):
        rtsp_url = stream_url
    else:
        rtsp_url = _build_rtsp_url(
            settings.get(f"kiosk_camera_host_{stream_id}") or "",
            settings.get(f"kiosk_camera_user_{stream_id}") or "",
            settings.get(f"kiosk_camera_password_{stream_id}") or "",
        )

    if not rtsp_url:
        return ("", 404)
    if not shutil.which("ffmpeg"):
        return ("ffmpeg not available", 503)

    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-rtsp_transport",
        "tcp",
        "-i",
        rtsp_url,
        "-an",
        "-vf",
        "fps=5",
        "-q:v",
        "5",
        "-f",
        "mpjpeg",
        "-",
    ]
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        bufsize=0,
    )

    def generate():
        try:
            while True:
                chunk = process.stdout.read(4096)
                if not chunk:
                    break
                yield chunk
        finally:
            process.kill()
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                process.kill()

    return Response(
        stream_with_context(generate()),
        mimetype="multipart/x-mixed-replace; boundary=ffmpeg",
        headers={"Cache-Control": "no-store"},
    )
