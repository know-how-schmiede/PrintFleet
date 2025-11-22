#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from flask import Blueprint

bp = Blueprint("settings", __name__)

# Routen importieren
from . import routes  # noqa: E402,F401