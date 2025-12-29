# PrintFleet Setup Scripts (Debian 13 LXC)

This folder contains Bash scripts:

- `setupPrintFleet` installs PrintFleet inside an existing Debian 13 LXC container.
- `setupPrintFleetService` installs PrintFleet as a systemd service.
- `setupPrintFleetTelegram` configures the Telegram bot token and chat ID.
- `updatePrintFleetService` updates the repo and restarts the service.
- `CleanGitLokalRepo` removes ignored temp files from the repo (safe cleanup).

Both scripts are designed for beginners. You can press Enter to accept defaults.

## Prerequisites

- Debian 13 LXC container already created in Proxmox.
- You are logged in as `root` in the container console (directly after login).
- Internet access from the container (to install packages and Python deps).

## Quick Start (recommended)

1. Update the container and install git:

```bash
apt update && apt -y upgrade
apt -y install git
```

2. Clone the PrintFleet repo (example path):

```bash
git clone https://github.com/know-how-schmiede/PrintFleet.git /opt/printfleet
```

3. Make the scripts executable:

```bash
chmod +x /opt/printfleet/scripts/setupPrintFleet \
  /opt/printfleet/scripts/setupPrintFleetService \
  /opt/printfleet/scripts/setupPrintFleetTelegram \
  /opt/printfleet/scripts/updatePrintFleetService \
  /opt/printfleet/scripts/CleanGitLokalRepo
```

4. Run the installer:

```bash
/opt/printfleet/scripts/setupPrintFleet
```

The script will:

- Install required system packages
- Create the `printfleet` user (if missing)
- Create a Python virtual environment
- Install Python dependencies
- Optionally start PrintFleet for a test run

After the test starts, open:

```
http://<container-ip>:8080
```

Stop the test with Ctrl+C.

## Install the Service (after the test)

```bash
/opt/printfleet/scripts/setupPrintFleetService
```

Check status:

```bash
systemctl status printfleet
```

## Start PrintFleet Manually (no service)

```bash
cd /opt/printfleet/src && /opt/printfleet/.venv/bin/python PrintFleetDB.py
```

Stop with Ctrl+C.

## Update PrintFleet

Recommended:

```bash
/opt/printfleet/scripts/updatePrintFleetService
```

This also updates Python dependencies in the venv if available.

If you want to avoid auto-stashing local changes:

```bash
/opt/printfleet/scripts/updatePrintFleetService --no-stash
```

If you want to keep Python cache files:

```bash
/opt/printfleet/scripts/updatePrintFleetService --skip-clean-pyc
```

Manual:

```bash
cd /opt/printfleet && git pull
systemctl restart printfleet
```

## Cleanup before updates (optional)

If you see update errors caused by leftover temp files, run:

```bash
/opt/printfleet/scripts/CleanGitLokalRepo
```

The script shows a preview and only removes ignored files after confirmation.

## Configure Telegram

```bash
/opt/printfleet/scripts/setupPrintFleetTelegram
```

This writes a systemd drop-in for `PRINTFLEET_TELEGRAM_TOKEN`, updates the
Telegram chat ID in the database, and restarts the service.
