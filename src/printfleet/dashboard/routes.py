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
    kiosk_stream_url = settings.get("kiosk_stream_url") or ""
    kiosk_stream_is_rtsp = kiosk_stream_url.lower().startswith("rtsp://")
    kiosk_camera_host = settings.get("kiosk_camera_host") or ""
    kiosk_camera_user = settings.get("kiosk_camera_user") or ""
    kiosk_camera_password = settings.get("kiosk_camera_password") or ""
    kiosk_show_iframe = bool(kiosk_stream_url and not kiosk_stream_is_rtsp)
    kiosk_show_mjpeg = kiosk_stream_is_rtsp or (
        kiosk_camera_host and kiosk_camera_user and kiosk_camera_password
    )
    return render_template(
        "kiosk.html",
        page="kiosk",
        kiosk_stream_url=kiosk_stream_url if kiosk_show_iframe else "",
        kiosk_show_iframe=kiosk_show_iframe,
        kiosk_show_mjpeg=kiosk_show_mjpeg,
    )


@bp.route("/api/kiosk/status")
def kiosk_status():
    return jsonify(_sorted_printer_rows())


@bp.route("/kiosk/stream.mjpg")
def kiosk_stream():
    settings = load_settings_from_db()
    stream_url = settings.get("kiosk_stream_url") or ""
    if stream_url.lower().startswith("rtsp://"):
        rtsp_url = stream_url
    else:
        rtsp_url = _build_rtsp_url(
            settings.get("kiosk_camera_host") or "",
            settings.get("kiosk_camera_user") or "",
            settings.get("kiosk_camera_password") or "",
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
