# tasmota_power.py
import requests

def tasmota_get_state(ip: str) -> str:
    """
    Liefert 'ON', 'OFF' oder 'UNKNOWN' zurück.
    """
    if not ip:
        return "UNKNOWN"

    url = f"http://{ip}/cm?cmnd=Power"
    try:
        r = requests.get(url, timeout=3)
        if r.status_code != 200:
            return "UNKNOWN"

        data = r.json()
        # Tasmota nutzt meist "POWER" oder "POWER1"
        for key, value in data.items():
            if key.upper().startswith("POWER"):
                return str(value).upper()
        return "UNKNOWN"
    except Exception as e:
        print(f"Tasmota Status-Fehler für {ip}: {e}")
        return "UNKNOWN"


def tasmota_set_state(ip: str, on: bool) -> bool:
    """
    Schaltet die Steckdose AN (on=True) oder AUS (on=False).
    """
    if not ip:
        return False

    cmd = "On" if on else "Off"
    url = f"http://{ip}/cm?cmnd=Power%20{cmd}"
    try:
        r = requests.get(url, timeout=3)
        if r.status_code != 200:
            return False
        # Optional prüfen, ob Rückgabe wirklich dem gewünschten Zustand entspricht
        data = r.json()
        for key, value in data.items():
            if key.upper().startswith("POWER"):
                return str(value).upper() == ("ON" if on else "OFF")
        return True
    except Exception as e:
        print(f"Tasmota Schalt-Fehler für {ip}: {e}")
        return False