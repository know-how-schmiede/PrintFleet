#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from flask import render_template

from printfleet.i18n import _
from . import bp


@bp.route("/")
def info_page() -> str:
    """
    Einfache Info-/About-Seite für PrintFleet.
    Die Version kommt als `app_version` aus dem Context Processor in PrintFleetDB.py.
    """
    return render_template(
        "info.html",
        page="info",  # für aktiven Menüpunkt in base.html
    )