#!/usr/bin/env bash
set -euo pipefail

if command -v ffmpeg >/dev/null 2>&1; then
  echo "ffmpeg already installed."
  exit 0
fi

if ! command -v apt-get >/dev/null 2>&1; then
  echo "apt-get not found. Install ffmpeg manually for your distribution." >&2
  exit 1
fi

SUDO=""
if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  if command -v sudo >/dev/null 2>&1; then
    SUDO="sudo"
  else
    echo "Please run as root or install sudo." >&2
    exit 1
  fi
fi

echo "Installing ffmpeg..."
$SUDO apt-get update
$SUDO apt-get install -y ffmpeg

echo "Done. ffmpeg installed."
