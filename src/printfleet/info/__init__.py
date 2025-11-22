#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from flask import Blueprint

bp = Blueprint("info", __name__, url_prefix="/info")

from . import routes  # noqa: E402,F401