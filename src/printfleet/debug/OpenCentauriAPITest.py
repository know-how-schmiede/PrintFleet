#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import websocket
import json
import threading
import time
import socket
import signal
import sys

# ==============================================
# GLOBAL CTRL+C HANDLING
# ==============================================
running = True  # global flag

def signal_handler(sig, frame):
    global running
    print("\n🛑 CTRL+C erkannt – beende Script…")
    running = False
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)


# ==============================================
# DISCOVERY VIA UDP BROADCAST
# ==============================================
BROADCAST_ADDR = ("192.168.1.255", 3000)
DISCOVER_MSG = "M99999"

def discover_centauri():
    """Sendet UDP-Broadcast und sucht den Elegoo Centauri Carbon."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.settimeout(2)

    print("🔍 Sende Discovery Broadcast…")
    sock.sendto(DISCOVER_MSG.encode(), BROADCAST_ADDR)

    try:
        data, addr = sock.recvfrom(4096)
        response = json.loads(data.decode())
        ip = response["Data"]["MainboardIP"]
        print(f"✔ Centauri gefunden @ {ip}")
        return ip
    except socket.timeout:
        print("⚠ Kein Gerät gefunden.")
        return None
    finally:
        sock.close()


# ==============================================
# WEBSOCKET SDCP CLIENT
# ==============================================
class CentauriWS:
    def __init__(self, ip):
        self.url = f"ws://{ip}:3030/websocket"
        self.ws = None
        self.connected = False
        self.should_reconnect = True

    # ------------------------------------------
    # WebSocket Nachricht empfangen
    # ------------------------------------------
    def on_message(self, ws, msg):
        try:
            parsed = json.loads(msg)
            print("\n📩 Eingehend:", json.dumps(parsed, indent=2))
        except:
            print("\n📩 RAW:", msg)

    # ------------------------------------------
    # Nach Verbindungsaufbau
    # ------------------------------------------
    def on_open(self, ws):
        print("🔌 WebSocket verbunden.")
        self.connected = True

        # 1) Handshake
        handshake = {
            "Cmd": 0,
            "Type": 1,
            "Timestamp": int(time.time() * 1000)
        }
        ws.send(json.dumps(handshake))
        print("🤝 Handshake gesendet.")

        # 2) Subscription
        subscribe = {
            "Cmd": 1,
            "Type": 1,
            "Topics": [
                "sdcp/status/+",
                "sdcp/printing/+",
                "sdcp/system/+",
                "sdcp/event/+"
            ]
        }
        ws.send(json.dumps(subscribe))
        print("📡 Topics abonniert.")

        # 3) Heartbeat Thread starten
        threading.Thread(target=self.heartbeat_loop, daemon=True).start()

    # ------------------------------------------
    # Heartbeat-Schleife
    # ------------------------------------------
    def heartbeat_loop(self):
        while running and self.connected:
            hb = {
                "Cmd": 255,
                "Type": 1,
                "Timestamp": int(time.time() * 1000)
            }
            try:
                self.ws.send(json.dumps(hb))
                print("❤️ Heartbeat gesendet")
            except:
                break
            time.sleep(8)

    # ------------------------------------------
    # Licht ein/aus (SecondLight)
    # ------------------------------------------
    def set_light(self, on=True):
        """Schaltet die Arbeitsraum-Beleuchtung des Centauri Carbon."""
        cmd = {
            "Cmd": 129,
            "Type": 1,
            "Data": {
                "LightStatus": {
                    "SecondLight": 1 if on else 0
                }
            },
            "Timestamp": int(time.time() * 1000)
        }

        try:
            self.ws.send(json.dumps(cmd))
            print(f"💡 Licht {'AN' if on else 'AUS'} gesendet")
        except Exception as e:
            print("⚠ Fehler beim Licht-Kommando:", e)


    # ------------------------------------------
    # Verbindung beendet
    # ------------------------------------------
    def on_close(self, ws, code, reason):
        print("❌ WebSocket geschlossen:", code, reason)
        self.connected = False

        if running and self.should_reconnect:
            print("🔄 Reconnect in 2 Sekunden…")
            time.sleep(2)
            self.connect()

    # ------------------------------------------
    # Fehlerbehandlung
    # ------------------------------------------
    def on_error(self, ws, error):
        print("❗ WebSocket Fehler:", error)

    # ------------------------------------------
    # Verbindung starten
    # ------------------------------------------
    def connect(self):
        if not running:
            return

        print(f"🔗 Verbinde mit WebSocket {self.url} …")
        self.ws = websocket.WebSocketApp(
            self.url,
            on_open=self.on_open,
            on_message=self.on_message,
            on_close=self.on_close,
            on_error=self.on_error
        )

        try:
            self.ws.run_forever()
        except KeyboardInterrupt:
            print("\n🛑 KeyboardInterrupt – Script wird beendet.")
            self.should_reconnect = False
            sys.exit(0)


# ==============================================
# HAUPTPROGRAMM
# ==============================================
def main():
    print("=== OpenCentauri WebSocket API Analyzer – Komplett v5 ===")

    # 1) Gerät suchen
    ip = None
    while running and ip is None:
        ip = discover_centauri()
        if ip is None:
            time.sleep(2)

    # 2) WebSocket starten
    ws = CentauriWS(ip)

    # separate Thread starten, damit wir nach Verbindung Aktionen durchführen können
    threading.Thread(target=ws.connect, daemon=True).start()

    # Warten bis WebSocket verbunden ist
    while not ws.connected and running:
        time.sleep(0.2)

    # 3) LICHTTEST: 5 Sekunden AN → AUS
    if ws.connected:
        print("\n⭐ Starte Licht-Test…")
        ws.set_light(True)
        time.sleep(5)
        ws.set_light(False)
        print("⭐ Licht-Test abgeschlossen.\n")

    # Hauptthread offen halten
    while running:
        time.sleep(1)


if __name__ == "__main__":
    main()
