#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from flask import Blueprint

bp = Blueprint("dashboard", __name__)

from . import routes  # noqa: E402,F401