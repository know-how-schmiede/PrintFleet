#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from flask import Blueprint

bp = Blueprint("printers", __name__)

# Die eigentlichen Routen kommen in routes.py
from . import routes  # noqa: E402,F401