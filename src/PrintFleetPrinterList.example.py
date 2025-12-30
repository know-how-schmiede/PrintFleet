# Copy this file to PrintFleetPrinterList.py and adjust values for your setup.

GLOBAL = {
    "interval": 5.0,             # polling interval in seconds
    "print_interval": 30.0,      # console output interval
    "error_report_interval": 30.0,
    "port": 80,                  # default port
    "https": False,
}

PRINTERS = [
    {
        "name": "Example Moonraker",
        "backend": "moonraker",
        "host": "192.168.1.100",
        "port": 80,
        # "token": "YOUR_TOKEN",
        # "https": False,
    },
    {
        "name": "Example OctoPrint",
        "backend": "octoprint",
        "host": "192.168.1.101",
        "port": 5000,
        "api_key": "YOUR_OCTOPRINT_API_KEY",
        # "https": False,
    },
]
