#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from flask import Blueprint

bp = Blueprint("legal", __name__, url_prefix="/legal")

from . import routes  # noqa: E402,F401
