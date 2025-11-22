#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from flask import current_app
from . import bp


@bp.route("/debug_routes")
def debug_routes() -> str:
    """Einfache Übersicht aller registrierten Routes anzeigen."""
    lines = []
    for rule in current_app.url_map.iter_rules():
        lines.append(f"{rule.endpoint} -> {rule.rule}")
    return "<br>".join(sorted(lines))