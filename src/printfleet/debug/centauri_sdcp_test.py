#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time
import json
import websocket  # pip install websocket-client
import traceback

CENTURI_IP = "192.168.1.233"   # <<< hier IP eintragen
PORT = 3030                    # SDCP-Port
WS_PATH = "/websocket"         # Standard-Pfad – später testen wir andere Pfade

RECONNECT_DELAY = 3            # Sekunden warten vor erneutem Verbinden
PING_INTERVAL = 5              # alle 5 Sekunden Ping senden


def connect_ws():
    url = f"ws://{CENTURI_IP}:{PORT}{WS_PATH}"
    print(f"\n[INFO] Verbinde zu: {url}")
    ws = websocket.create_connection(url, timeout=10)  # 10 Sekunden Timeout beim Verbinden
    print("[OK] WebSocket-Verbindung aufgebaut.")
    return ws


def run_sdcp_test():
    ws = None
    last_ping = 0

    while True:
        # Verbindung herstellen falls nicht vorhanden
        if ws is None:
            try:
                ws = connect_ws()
            except Exception as e:
                print(f"[ERROR] Konnte WebSocket nicht verbinden: {e}")
                traceback.print_exc()
                print(f"[INFO] Neuer Verbindungsversuch in {RECONNECT_DELAY}s …")
                time.sleep(RECONNECT_DELAY)
                continue

        # Ping schicken?
        if time.time() - last_ping > PING_INTERVAL:
            try:
                ws.send("ping")
                print("[PING] -> ping")
            except Exception as e:
                print(f"[ERROR] Ping fehlgeschlagen: {e}")
                ws = None
                continue
            last_ping = time.time()

        # Nachricht vom Drucker empfangen
        try:
            raw = ws.recv()  # blockiert bis Timeout oder Nachricht
        except Exception as e:
            print(f"[ERROR] recv() fehlgeschlagen: {e}")
            ws = None  # Verbindung verloren → reconnect
            continue

        print(f"\n[RECV] {raw}")

        # JSON versuchen
        try:
            obj = json.loads(raw)
        except Exception:
            continue  # keine JSON → ignorieren

        # Status-Meldung erkannt?
        if isinstance(obj, dict) and "Status" in obj:
            status = obj["Status"]
            print("\n=== STATUS ===")
            print(json.dumps(status, indent=2))

            pi = status.get("PrintInfo", {})
            print("== PrintInfo ==")
            print(json.dumps(pi, indent=2))
            print("================\n")


if __name__ == "__main__":
    print("=== Elegoo Centauri / Centurio SDCP Testclient ===")
    print("Mit STRG+C beenden.")
    run_sdcp_test()
