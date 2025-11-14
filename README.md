![PrintFleet Logo](images/PrintFleetLogo.png)

# PrintFleet - Manage your 3D printer fleet
Zentrale Verwaltung und Monitoring einer 3D-Drucker-Farm

PrintFleet ist eine Web-Anwendung zur Überwachung, Steuerung und Dokumentation mehrerer 3D-Drucker innerhalb einer Drucker-Farm.
Das Projekt befindet sich aktuell in aktiver Entwicklung und dient als Basis für ein skalierbares, modular aufgebautes Drucker-Management-System.

## 🚀 Aktueller Entwicklungsstand
✔ Web-Interface (Flask)
- Übersicht aller registrierten Drucker
- Darstellung des aktuellen Status (Online/Offline)
- Übersichtliches Dashboard
- Integration eines Logos
- Strukturierte Navigationsleiste und sauberes Layout

✔ Datenhaltung (SQLite)
- Benutzerverwaltung (Registrierung, Login, Rollen erweiterbar)
- Speicherung von Drucker-Informationen:
- Name des Druckers
- Klipper-IP
- IP-Adresse der zugewiesenen Tasmota-Steckdose
- Geplante Erweiterbarkeit (Temperaturen, Aufträge, Logs)

✔ Infrastruktur & Installation
- Basis-Setup-Anleitung für Debian 13 LXC auf Proxmox
- Repository kann bereits geklont und lokal gestartet werden
- SSH-Unterstützung (z. B. PuTTY)
- Flask-Server läuft lokal auf Port 5000

✔ Tasmota-Integration (Grundlage)
- Hinterlegung der Steckdosen pro Drucker
- Vorbereitung für API-basierte Schaltbefehle (Ein/Aus)

## 🛠 Ziel des Projekts
PrintFleet soll eine modulare, erweiterbare Plattform sein, mit der 3D-Drucker-Farmen zuverlässig verwaltet werden können.
Im Fokus stehen:
- Automatisierung
- Übersichtliche Darstellung
- Erweiterbarkeit
- Einfache Installation
- Integration gängiger Maker-Tools

## 🌱 Roadmap – Geplante Erweiterungen
### 🔧 1. Drucker-Management
- Automatisches Erkennen neuer Drucker
- Live-Daten aus Klipper (Temperatur, Bewegungen, Fehler)
- Temperaturverläufe und Statusgrafiken
- Druckhistorie, Statistiken, Log-Daten

### 🔌 2. Energieverwaltung
- Schalten der Drucker über Tasmota
- Automatisches Abschalten nach Druckende
- Regeln (z. B. Zeitsteuerung, Sicherheitsabschaltung)

### 📊 3. Monitoring & Logging
- Grafische Auswertungen (Grafana oder integrierte Diagramme)
- Speicherung aller Druckaufträge
- Fehlerüberwachung (Klipper-Errors, Filament-Runout)

### 👤 4. Benutzerverwaltung
- Rollen & Rechte
- Mehrbenutzer-System
- API-Key-Management

### 🔗 5. Schnittstellen
- REST-API für externe Tools
- MQTT-Integration (Tasmota, Sensoren)
- Webhooks (Discord, Matrix, E-Mail)

### 🧩 6. Plugin-System
- Erweiterungen für verschiedene Druckermodelle
- Automatische Tests, Reinigung, Kalibrierung
- Add-ons für spezielle Statistiken

### 🖥 7. Installation & Deployment
- Einfache Setup-Skripte
- Docker-Container
- One-Click-Installer über GitHub Releases

## Lizenz
------
Der Quellcode dieses Projekts steht unter der Lizenz **CC BY-NC-SA 4.0**.

Das bedeutet:
- freie Nutzung für Privatpersonen
- freie Nutzung zu Bildungs- und Forschungszwecken
- Weitergabe und Änderungen sind erlaubt
- keine kommerzielle Nutzung ohne meine ausdrückliche Zustimmung
- Der Quellcode darf nicht verkauft werden

Für kommerzielle Nutzung kontaktieren Sie bitte den Autor.
