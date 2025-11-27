#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from flask import Blueprint

bp = Blueprint("debug", __name__)

# Routen importieren, damit sie beim Import des Blueprints registriert werden
from . import routes  # noqa: E402,F401
from . import telegram_test  # noqa: E402,F401