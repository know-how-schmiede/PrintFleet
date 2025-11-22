#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import threading
from typing import Dict, Any

# Globaler Lock für den Zugriff auf printer_state
state_lock = threading.Lock()

# Gemeinsamer Status aller Drucker
printer_state: Dict[str, Dict[str, Any]] = {}