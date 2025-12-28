#!/usr/bin/env python3
"""
Aktiver LAN-Scanner fuer OctoPrint-, Klipper- und Elegoo-Centurio-Installationen.
Scant IPv4-Netze auf typische Ports und gibt gefundene Hosts aus.
"""
from __future__ import annotations

import argparse
import json
import ipaddress
import logging
import os
import socket
import ssl
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from typing import Dict, Iterable, List, Mapping, Sequence

# Bekannte Ziele und ihre typischen Ports/Signaturen.
TARGETS = {
    "OctoPrint": {
        "ports": {80, 443, 5000},
        # Starke Indikatoren, auch ohne HTTP-Text
        "strong_ports": {5000},
        "http_keywords": (
            "octoprint",
            "x-clacks-overhead",
            "permissions=status,settings_read",
            "/login/?redirect=",
        ),
    },
    "Klipper": {
        "ports": {80, 443, 8080, 7125},
        "strong_ports": {7125},
        "http_keywords": ("moonraker", "klipper", "mainsail", "fluidd"),
    },
    "Elegoo Centurio": {
        # Centurio Carbon spricht ueber Moonraker/Fluidd, teilt daher Ports mit Klipper
        "ports": {80, 443, 8080, 7125},
        "strong_ports": {7125},
        "http_keywords": ("elegoo", "centurio", "moonraker", "fluidd"),
    },
}

UNIQUE_PORTS = sorted({p for cfg in TARGETS.values() for p in cfg["ports"]})
HTTP_PORTS = {80, 443, 5000, 7125, 8080}
EXTRA_HTTP_PATHS = ("/api/version", "/server/info")
LOGGER = logging.getLogger("lan_scan")


def get_local_ipv4s() -> List[str]:
    """Sammelt lokale IPv4-Adressen ohne externen Netzwerkzugriff."""
    addresses: set[str] = set()
    try:
        hostname = socket.gethostname()
        for family, _, _, _, sockaddr in socket.getaddrinfo(hostname, None):
            if family != socket.AF_INET:
                continue
            ip = sockaddr[0]
            if ip.startswith(("127.", "169.254.")):
                continue
            addresses.add(ip)
    except OSError:
        LOGGER.exception("Fehler beim Aufloesen lokaler IPv4-Adressen.")
        pass
    if addresses:
        LOGGER.debug("Lokale IPv4-Adressen: %s", ", ".join(sorted(addresses)))
    return sorted(addresses)


def guess_networks(
    default_cidr: str = "192.168.0.0/24",
) -> List[ipaddress.IPv4Network]:
    """Versucht, lokale /24-Netze anhand aktiver IPs zu raten."""
    candidates: List[str] = []
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            candidates.append(sock.getsockname()[0])
    except OSError:
        LOGGER.debug("Keine externe UDP-Verbindung fuer Netz-Erkennung moeglich.")
        pass

    candidates.extend(get_local_ipv4s())
    if candidates:
        LOGGER.debug("Netz-Kandidaten: %s", ", ".join(candidates))

    networks: List[ipaddress.IPv4Network] = []
    seen: set[str] = set()
    for ip in candidates:
        octets = ip.split(".")
        if len(octets) != 4 or ip.startswith(("127.", "169.254.")):
            continue
        cidr = ".".join(octets[:3]) + ".0/24"
        try:
            network = ipaddress.ip_network(cidr, strict=False)
        except ValueError:
            continue
        key = network.with_prefixlen
        if key in seen:
            continue
        seen.add(key)
        networks.append(network)

    if not networks:
        networks.append(ipaddress.ip_network(default_cidr, strict=False))
        LOGGER.debug("Fallback-Netz gesetzt: %s", networks[0])

    return networks


def is_port_open(ip: str, port: int, timeout: float) -> bool:
    """Prueft, ob ein Port via TCP erreichbar ist."""
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            LOGGER.debug("Offener Port %s:%s", ip, port)
            return True
    except OSError:
        return False


def read_http_banner(ip: str, port: int, timeout: float, path: str = "/") -> str:
    """Holt einen kurzen HTTP-Banner fuer die Erkennung."""
    request = (
        f"GET {path} HTTP/1.0\r\n"
        f"Host: {ip}\r\n"
        "User-Agent: LanScan/1.0\r\n"
        "Connection: close\r\n\r\n"
    ).encode()

    try:
        with socket.create_connection((ip, port), timeout=timeout) as raw_sock:
            raw_sock.settimeout(timeout)
            if port == 443:
                context = ssl.create_default_context()
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE
                with context.wrap_socket(raw_sock, server_hostname=ip) as tls_sock:
                    tls_sock.sendall(request)
                    return tls_sock.recv(2048).decode(errors="ignore").lower()

            raw_sock.sendall(request)
            banner = raw_sock.recv(2048).decode(errors="ignore").lower()
            if banner:
                LOGGER.debug(
                    "HTTP-Banner %s:%s %s: %s",
                    ip,
                    port,
                    path,
                    banner[:160],
                )
            return banner
    except (OSError, ssl.SSLError):
        return ""


def classify(ip: str, open_port: int, banner: str) -> Mapping[str, List[int]]:
    """Ordnet geoeffnete Ports OctoPrint/Klipper zu."""
    found: Dict[str, List[int]] = {}
    for name, cfg in TARGETS.items():
        if open_port not in cfg["ports"]:
            continue
        if open_port in cfg["strong_ports"]:
            found.setdefault(name, []).append(open_port)
            continue
        if banner and any(keyword in banner for keyword in cfg["http_keywords"]):
            found.setdefault(name, []).append(open_port)
    if found:
        services = ", ".join(sorted(found))
        LOGGER.debug("Treffer %s via Port %s: %s", ip, open_port, services)
    return found


def probe_host(ip: str, timeout: float) -> Mapping[str, List[int]]:
    """Scant einen Host ueber alle bekannten Ports."""
    matches: Dict[str, List[int]] = {}
    LOGGER.debug("Scanne Host %s", ip)
    for port in UNIQUE_PORTS:
        if not is_port_open(ip, port, timeout):
            continue
        banner = read_http_banner(ip, port, timeout) if port in HTTP_PORTS else ""
        classified = classify(ip, port, banner)
        if not classified and port in HTTP_PORTS:
            for path in EXTRA_HTTP_PATHS:
                extra_banner = read_http_banner(ip, port, timeout, path=path)
                if not extra_banner:
                    continue
                classified = classify(ip, port, extra_banner)
                if classified:
                    break

        for name, ports in classified.items():
            matches.setdefault(name, []).extend(ports)
    return matches


def scan_network(
    network: ipaddress.IPv4Network,
    timeout: float,
    workers: int,
    show_progress: bool = True,
) -> Mapping[str, Dict[str, List[int]]]:
    """Scannt ein Netz parallel und sammelt Treffer."""
    hits: Dict[str, Dict[str, List[int]]] = {name: {} for name in TARGETS}
    addresses: List[str] = [str(ip) for ip in network.hosts()]
    total = len(addresses)
    progress = 0
    lock = Lock()

    LOGGER.info("Starte Scan fuer %s (%s Hosts).", network, total)
    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_map = {
            executor.submit(probe_host, ip, timeout): ip for ip in addresses
        }
        for future in as_completed(future_map):
            ip = future_map[future]
            try:
                result = future.result()
            except Exception:
                LOGGER.exception("Fehler beim Scan von %s", ip)
                continue

            for name, ports in result.items():
                hits[name][ip] = sorted(set(ports))

            with lock:
                progress += 1
                render_progress(progress, total, show_progress)

    return hits


def scan_hosts(
    hosts: Sequence[str],
    timeout: float,
    workers: int,
    show_progress: bool = True,
) -> Mapping[str, Dict[str, List[int]]]:
    """Scannt eine feste Hostliste parallel und sammelt Treffer."""
    hits: Dict[str, Dict[str, List[int]]] = {name: {} for name in TARGETS}
    addresses = [host.strip() for host in hosts if host.strip()]
    total = len(addresses)
    progress = 0
    lock = Lock()

    if addresses:
        LOGGER.info("Starte Scan fuer Hosts: %s", ", ".join(addresses))
    else:
        LOGGER.info("Keine Hosts zum Scannen erhalten.")
        return hits

    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_map = {
            executor.submit(probe_host, ip, timeout): ip for ip in addresses
        }
        for future in as_completed(future_map):
            ip = future_map[future]
            try:
                result = future.result()
            except Exception:
                LOGGER.exception("Fehler beim Scan von %s", ip)
                continue

            for name, ports in result.items():
                hits[name][ip] = sorted(set(ports))

            with lock:
                progress += 1
                render_progress(progress, total, show_progress)

    return hits


def merge_hits(
    target: Dict[str, Dict[str, List[int]]],
    source: Mapping[str, Dict[str, List[int]]],
) -> None:
    """Fasst Treffer aus mehreren Scans zusammen."""
    for name, entries in source.items():
        for ip, ports in entries.items():
            existing = set(target.get(name, {}).get(ip, []))
            existing.update(ports)
            target.setdefault(name, {})[ip] = sorted(existing)


def build_results(found: Mapping[str, Dict[str, List[int]]]) -> List[Dict[str, object]]:
    """Normalisiert Treffer fuer JSON-Ausgabe."""
    results: List[Dict[str, object]] = []
    for name in TARGETS:
        service_hits = found.get(name, {})
        for ip, ports in service_hits.items():
            results.append(
                {
                    "type": name,
                    "ip": ip,
                    "ports": sorted(set(ports)),
                }
            )
    results.sort(key=lambda entry: (entry["type"], entry["ip"]))
    return results


def print_summary(found: Mapping[str, Dict[str, List[int]]]) -> None:
    """Gibt gefundene IPs je Dienst aus."""
    any_hits = False
    for name in TARGETS:
        service_hits = found.get(name, {})
        if not service_hits:
            continue
        any_hits = True
        print(f"{name}:")
        for ip in sorted(service_hits):
            port_list = ", ".join(str(p) for p in service_hits[ip])
            print(f"  {ip} (Ports: {port_list})")

    if not any_hits:
        print("Keine OctoPrint- oder Klipper-Hosts gefunden.")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Aktiver OctoPrint/Klipper LAN-Scanner."
    )
    parser.add_argument(
        "--cidr",
        help="Optionales Netz in CIDR-Notation (z.B. 192.168.178.0/24). "
        "Mehrere Netze koennen komma-getrennt angegeben werden. "
        "Ohne Angabe werden lokale /24-Netze geraten.",
    )
    parser.add_argument(
        "--hosts",
        help="Optionale Hostliste (IP oder Name), komma-getrennt. "
        "Wenn gesetzt, wird nur diese Liste gescannt.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=0.6,
        help="Timeout pro Port (Sekunden).",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=64,
        help="Parallelitaet (Threads) fuer den Scan.",
    )
    parser.add_argument(
        "--log",
        default="lan_scan.log",
        help="Pfad zur Debug-Logdatei (Standard: lan_scan.log im Skript-Ordner).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Gibt die Ergebnisse als JSON aus.",
    )
    parser.add_argument(
        "--no-progress",
        action="store_true",
        help="Kein Fortschrittsbalken.",
    )
    return parser.parse_args(argv)


def render_progress(done: int, total: int, enabled: bool = True) -> None:
    """Gibt einen einfachen Fortschrittsbalken aus."""
    if not enabled:
        return
    if total <= 0:
        return
    bar_len = 30
    pct = int((done / total) * 100)
    filled = int(bar_len * done / total)
    bar = "#" * filled + "-" * (bar_len - filled)
    sys.stdout.write(f"\rFortschritt [{bar}] {done}/{total} ({pct}%)")
    sys.stdout.flush()
    if done >= total:
        sys.stdout.write("\n")


def main() -> None:
    args = parse_args()
    script_dir = os.path.dirname(os.path.abspath(__file__))
    log_path = (
        args.log if os.path.isabs(args.log) else os.path.join(script_dir, args.log)
    )
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(log_path, mode="w", encoding="utf-8")],
    )
    LOGGER.info("Logdatei: %s", log_path)

    show_progress = not args.no_progress and not args.json
    hosts: List[str] = []
    networks: List[ipaddress.IPv4Network] = []
    if args.hosts:
        hosts = [host.strip() for host in args.hosts.split(",") if host.strip()]
        if hosts and not args.json:
            host_list = ", ".join(hosts)
            print(f"Scanne Hosts {host_list} auf OctoPrint/Klipper ...")
        found = scan_hosts(
            hosts,
            timeout=args.timeout,
            workers=args.workers,
            show_progress=show_progress,
        )
    else:
        if args.cidr:
            cidr_list = [cidr.strip() for cidr in args.cidr.split(",") if cidr.strip()]
            networks = [ipaddress.ip_network(cidr, strict=False) for cidr in cidr_list]
        else:
            networks = guess_networks()

        if not args.json:
            if len(networks) == 1:
                print(f"Scanne Netz {networks[0]} auf OctoPrint/Klipper ...")
            else:
                net_list = ", ".join(str(net) for net in networks)
                print(f"Scanne Netze {net_list} auf OctoPrint/Klipper ...")

        found = {name: {} for name in TARGETS}
        for network in networks:
            merge_hits(
                found,
                scan_network(
                    network,
                    timeout=args.timeout,
                    workers=args.workers,
                    show_progress=show_progress,
                ),
            )
    if args.json:
        payload = {
            "results": build_results(found),
        }
        if args.hosts:
            payload["hosts"] = hosts
        else:
            payload["networks"] = [str(net) for net in networks]
        print(json.dumps(payload))
    else:
        print_summary(found)


if __name__ == "__main__":
    main()
