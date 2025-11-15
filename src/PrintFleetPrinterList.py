# dashboardPrinterList.py

GLOBAL = {
    "interval": 5.0,             # Polling-Intervall Sekunden
    "print_interval": 30.0,      # für Konsolen-Output (hier egal)
    "error_report_interval": 30.0,
    "port": 80,                  # Moonraker hinter Fluidd/Mainsail meist 80; sonst 7125
    "https": False,
}

PRINTERS = [
    {
        "name": "Neptune4",
        "backend": "moonraker",
        "host": "192.168.1.236",
        "port": 80,
        # "token": "",        # optional
        # "https": False,
    },
    {
        "name": "Neptune4 Plus",
        "backend": "moonraker",
        "host": "192.168.1.242",
        "port": 80,
        # "token": "",        # optional
        # "https": False,
    },
    {
        "name": "Ender3 Pro",
        "backend": "octoprint",
        "host": "192.168.1.240",
        "port": 80,              # „nacktes“ OctoPrint oft 5000
        "api_key": "DEIN_OCTOPRINT_API_KEY",
        # "https": False,
    },
    {
        "name": "FL SUN SuperRacer",
        "backend": "octoprint",
        "host": "192.168.1.241",
        "port": 80,              # „nacktes“ OctoPrint oft 5000
        "api_key": "DEIN_OCTOPRINT_API_KEY",
        # "https": False,
    },
    {
        "name": "OctoYoda Q5",
        "backend": "octoprint",
        "host": "192.168.1.167",
        "port": 80,              # „nacktes“ OctoPrint oft 5000
        "api_key": "N0X5aHS_NmaMJCOjpt1ZVOVrAGaZ6-aVY8O_zhNLbj4",
        # "https": False,
    },
]
