#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
from pathlib import Path
from typing import Dict, Set


def load_json(path: Path) -> Dict[str, str]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def main():
    # Dieses Script liegt im Ordner: PrintFleet/tests/
    script_dir = Path(__file__).resolve().parent

    # Projektwurzel ist eine Ebene höher: PrintFleet/
    project_root = script_dir.parent

    # i18n-Ordner im Projekt
    i18n_dir = project_root / "src" / "i18n"

    print(f"Looking for i18n directory: {i18n_dir}")

    if not i18n_dir.is_dir():
        print(f"[ERROR] i18n directory not found: {i18n_dir}")
        return

    json_files = sorted(i18n_dir.glob("*.json"))
    if not json_files:
        print(f"[ERROR] No *.json files found in {i18n_dir}")
        return

    print(f"Found {len(json_files)} JSON files in {i18n_dir}:\n")
    for f in json_files:
        print(f"  - {f.name}")
    print()

    # Alle Keys pro Datei sammeln
    all_keys: Set[str] = set()
    file_keys: Dict[str, Set[str]] = {}

    for f in json_files:
        try:
            data = load_json(f)
        except Exception as e:
            print(f"[ERROR] Could not load {f.name}: {e}")
            continue

        if not isinstance(data, dict):
            print(f"[WARNING] {f.name} does not contain a JSON object at top level.")
            continue

        keys = set(data.keys())
        file_keys[f.name] = keys
        all_keys |= keys

    if not file_keys:
        print("[ERROR] No valid JSON language files loaded.")
        return

    print("=== Key statistics ===")
    for name, keys in file_keys.items():
        print(f"{name}: {len(keys)} keys")
    print(f"\nTotal unique keys across all files: {len(all_keys)}\n")

    # Für jede Datei: Fehlende & zusätzliche Keys
    print("=== Per-file differences ===\n")
    for name, keys in file_keys.items():
        missing = sorted(all_keys - keys)
        extra = sorted(keys - (all_keys - keys))

        print(f"--- {name} ---")
        if missing:
            print(f"  Missing keys ({len(missing)}):")
            for k in missing:
                print(f"    - {k}")
        else:
            print("  Missing keys: none")

        if extra:
            print(f"  Extra keys ({len(extra)}):")
            for k in extra:
                print(f"    - {k}")
        else:
            print("  Extra keys: none")
        print()

    # Prüfen, ob alle Dateien gleich viele Keys haben
    key_counts = {name: len(keys) for name, keys in file_keys.items()}
    unique_counts = set(key_counts.values())
    if len(unique_counts) == 1:
        print("✅ All language files contain the same number of keys.")
    else:
        print("⚠️ Some language files have different numbers of keys:")
        for name, count in key_counts.items():
            print(f"  - {name}: {count} keys")


if __name__ == "__main__":
    main()
