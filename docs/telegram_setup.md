# 📡 PrintFleet – Telegram Integration Setup
Einrichtung & Verwendung der Telegram-Benachrichtigungen für PrintFleet

## 📘 Inhaltsverzeichnis
Einleitung
1. Telegram Bot anlegen
2. Chat-ID ermitteln
3. Bot-Token als Umgebungsvariable setzen
3.1 Temporär in der Shell
3.2 Dauerhaft über systemd
4. Chat-ID in PrintFleet eintragen
5. Modulübersicht: Telegram in PrintFleet
6. Aktivierung des Telegram-Command-Loops
7. Bot-Kommandos
8. Automatische Startmeldungen
9. Troubleshooting
10. Funktionsprüfung

## Einleitung
PrintFleet unterstützt eine integrierte Telegram-Anbindung, um Benachrichtigungen und Statusabfragen direkt über einen Telegram-Bot zu erhalten.

Mit dieser Integration kannst du:

✔ Automatische Startmeldungen empfangen
✔ Druckerübersichten mit Farbstatus abrufen
✔ Über Botbefehle wie /status oder /info kommunizieren
✔ Den PrintFleet-Server überwachen – auch unterwegs

Diese Dokumentation beschreibt alle notwendigen Schritte, um die Telegram-Integration auf einem neuen Server oder nach einem Neuaufsetzen vollständig einzurichten.

## 1. Telegram Bot anlegen
Öffne Telegram
Suche nach @BotFather
Befehl senden:

/newbot


Name vergeben (z. B. „PrintFleet Bot“)

Nutzername festlegen (z. B. PrintFleetFarmBot)

BotFather zeigt ein Token:

123456789:AAFfbTQWQwbvCqa-APjP7qYrUQgq33bLxA0


→ Dieses Token wird später als Umgebungsvariable gespeichert.

# 2. Chat-ID ermitteln

Öffne den Chat mit deinem Bot

Sende eine beliebige Nachricht:

Hallo PrintFleet


Führe auf dem Server aus:

curl "https://api.telegram.org/botDEIN_TOKEN/getUpdates"


In der Antwort:

"chat": {
  "id": 123456789,
  "type": "private"
}


→ Diese Zahl ist deine Chat-ID.
Bei Gruppen beginnt sie häufig mit -100….

# 3. Bot-Token als Umgebungsvariable setzen

PrintFleet erwartet das Bot-Token in:

PRINTFLEET_TELEGRAM_TOKEN

### 3.1 Temporär in der Shell
export PRINTFLEET_TELEGRAM_TOKEN="123456789:DEIN_TELEGRAM_TOKEN"


Test:

echo $PRINTFLEET_TELEGRAM_TOKEN

### 3.2 Dauerhaft über systemd

Falls PrintFleet über einen Service läuft:

/etc/systemd/system/printfleet.service:

[Service]
Environment="PRINTFLEET_TELEGRAM_TOKEN=123456789:DEIN_TELEGRAM_TOKEN"


Dann:

sudo systemctl daemon-reload
sudo systemctl restart printfleet

## 4. Chat-ID in PrintFleet eintragen

PrintFleet öffnen (http://SERVER:8080/)

Menü Settings

Feld Telegram Chat-ID

Deine ID eintragen:

123456789


Speichern

Prüfen:

python3 - <<EOF
from printfleet.db import load_settings_from_db
print(load_settings_from_db())
EOF

## 5. Modulübersicht: Telegram in PrintFleet

PrintFleet nutzt drei dedizierte Module:

Datei	Inhalt
printfleet/telegram_bot.py	Grundfunktion send_telegram_message
printfleet/notifications.py	Statusmeldungen, Startmeldungen, /info
printfleet/telegram_commands.py	/status & /info per Telegram-Command-Loop

Diese Module arbeiten eng mit dem Monitor-System zusammen.

## 6. Aktivierung des Telegram-Command-Loops

In PrintFleetDB.py muss folgender Start-Thread aktiv sein:

from printfleet.telegram_commands import telegram_command_loop

telegram_thread = threading.Thread(
    target=telegram_command_loop,
    args=(global_stop_evt,),
    daemon=True,
)
telegram_thread.start()


Am Ende im Shutdown:

telegram_thread.join(timeout=2.0)


Dies ist im aktuellen Code bereits integriert.

## 7. Bot-Kommandos
/status

Antwortet mit:

Druckername

Backend (Moonraker / OctoPrint)

IP-Adresse

Status

🔵 druckt

🟢 bereit

🔴 offline

⚪ unbekannt

/info

Gibt Systeminformationen aus:

PrintFleet-Version

Uptime

Anzahl Drucker

verwendete Backends

Hostname

kurze Hilfe zu Befehlen

## 8. Automatische Startmeldungen

PrintFleet sendet beim Start:

Startmeldung

Druckerübersicht (nach 10 s)

zweite Druckerübersicht (nach 60 s)
→ Monitor hat dann alle Stati zuverlässig geladen

Beispiel:

🚀 PrintFleet wurde gestartet (Version 0.3.6)
🖨️ Aktuelle Drucker:
• Neptune 4 Plus – 🟢 Bereit
• OctoYoda Q5 – 🔴 Offline

## 9. Troubleshooting
❌ Keine Nachrichten kommen an

Checkliste:

echo $PRINTFLEET_TELEGRAM_TOKEN


Token gesetzt?

Internetzugang? (api.telegram.org)

Chat-ID korrekt?

Bot einmalig gestartet?

❌ /status oder /info reagieren nicht

Läuft der Telegram-Thread?
Startausgabe muss enthalten:

Telegram: Command-Loop gestartet (/status)


Keine parallelen getUpdates-Prozesse?

Richtigen Bot geöffnet?

❌ Status = "Keine Statusdaten"

Monitor läuft, aber erste Abfragen dauern 10–30 s

60 s-Nachricht enthält vollständige Daten

## 10. Funktionsprüfung

Nach erfolgreicher Einrichtung:

/status


→ liefert Druckerzustände

/info


→ liefert Systeminformationen

Du solltest z. B. so etwas bekommen:

ℹ️ PrintFleet Info
• Version: 0.3.6
• Uptime: 0h 23min
• Drucker insgesamt: 4
  - OctoPrint: 2
  - Moonraker: 2
• Server: printfleet-rpi4
