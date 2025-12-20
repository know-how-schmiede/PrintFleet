# PrintFleet Setup Scripts (Debian 13 LXC)

This folder contains two Bash scripts:

- `setupPrintFleet` installs PrintFleet inside an existing Debian 13 LXC container.
- `setupPrintFleetService` installs PrintFleet as a systemd service.
- `updatePrintFleetService` updates the repo and restarts the service.

Both scripts are designed for beginners. You can press Enter to accept defaults.

## Prerequisites

- Debian 13 LXC container already created in Proxmox.
- You are logged in as `root` in the container console.
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
cd /opt/printfleet/scripts
```

3. Make the scripts executable:

```bash
chmod +x setupPrintFleet setupPrintFleetService updatePrintFleetService
```

4. Run the installer:

```bash
./setupPrintFleet
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
./setupPrintFleetService
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
./updatePrintFleetService
```

If you want to avoid auto-stashing local changes:

```bash
./updatePrintFleetService --no-stash
```

If you want to keep Python cache files:

```bash
./updatePrintFleetService --skip-clean-pyc
```

Manual:

```bash
cd /opt/printfleet && git pull
systemctl restart printfleet
```
