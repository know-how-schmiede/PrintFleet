#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from flask import render_template, jsonify

from printfleet.state import state_lock, printer_state
from . import bp


@bp.route("/")
def index() -> str:
    # 'page' wird im Template benutzt, um den aktiven Menüpunkt zu markieren
    return render_template("index.html", page="overview")


@bp.route("/api/status")
def api_status():
    with state_lock:
        rows = [printer_state[k] for k in sorted(printer_state.keys())]
    return jsonify(rows)