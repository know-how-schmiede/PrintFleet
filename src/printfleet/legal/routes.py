#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from flask import render_template

from . import bp


@bp.route("/imprint")
def imprint() -> str:
    return render_template("imprint.html", page="imprint")


@bp.route("/privacy")
def privacy() -> str:
    return render_template("privacy.html", page="privacy")
