"""Inventory and controlled operations for QEMU VMs and LXC containers in Proxmox VE.

By default, the program performs only read-only queries and Nmap scans of
authorized IPs. Power and creation operations require ``--execute``
and exact confirmations inside the interactive menu.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import logging
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable, TypeVar
from urllib.parse import quote, urlsplit, urlunsplit

import requests
import urllib3
from dotenv import load_dotenv


LOGGER = logging.getLogger("proxmox_scanner")
DEFAULT_OUTPUT = "proxmox_scan.json"
DEFAULT_GEMINI_MODEL = "gemini-2.0-flash"
REQUEST_TIMEOUT_SECONDS = 30
GEMINI_MAX_RETRIES = 3
GEMINI_RETRY_DELAYS = (2, 5, 10)
T = TypeVar("T")

# Self-signed certificates are common on administration networks.
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class ProxmoxAPIError(RuntimeError):
    """Fatal error while querying the main Proxmox API."""


class OptionalEndpointError(RuntimeError):
    """Endpoint error that must not abort the inventory."""


def required_env(name: str) -> str:
    """Gets a required variable without revealing its contents in logs."""
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


def optional_env(name: str, default: str) -> str:
    """Return an optional environment variable without exposing its value."""
    return os.getenv(name, default).strip() or default


def env_bool(name: str, default: bool = False) -> bool:
    """Parse a boolean environment variable with explicit accepted values."""
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be true/false, yes/no, or 1/0")


def proxmox_base_url(host: str, port: str = "8006") -> str:
    """Normalize a Proxmox host or URL and append the configured API path."""
    normalized = host.strip().rstrip("/")
    if not normalized.startswith(("http://", "https://")):
        normalized = f"https://{normalized}:{port}"
    else:
        parsed = urlsplit(normalized)
        if parsed.port is None and port:
            hostname = parsed.hostname or ""
            if ":" in hostname and not hostname.startswith("["):
                hostname = f"[{hostname}]"
            netloc = f"{hostname}:{port}"
            normalized = urlunsplit(
                (parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment)
            ).rstrip("/")
    for suffix in ("/api2/json", "/api2/extjs", "/api2/html"):
        if normalized.endswith(suffix):
            normalized = normalized[: -len(suffix)]
            break
    return f"{normalized}/api2/json"


def proxmox_auth_header(user: str, token: str) -> str:
    """Build a PVE API token header from supported environment formats.

    PROXMOX_USER may be either ``user@realm`` or
    ``user@realm!token-id``. In the latter form, PROXMOX_TOKEN contains only
    the token secret, matching the format used by the project environment.
    """
    normalized_user = user.strip()
    normalized = token.strip()
    if normalized.startswith("PVEAPIToken="):
        normalized = normalized[len("PVEAPIToken=") :]

    if "!" in normalized_user:
        token_user, token_id = normalized_user.split("!", 1)
        if not token_user or not token_id:
            raise ValueError("PROXMOX_USER must use user@realm or user@realm!token-id.")
        if "!" in normalized:
            embedded_user, token_value = normalized.split("!", 1)
            if embedded_user != token_user:
                raise ValueError(
                    "PROXMOX_TOKEN contains a user different from PROXMOX_USER."
                )
            return f"PVEAPIToken={embedded_user}!{token_value}"
        return f"PVEAPIToken={token_user}!{token_id}={normalized}"

    if "!" in normalized:
        token_user, token_value = normalized.split("!", 1)
        if token_user != normalized_user:
            raise ValueError(
                "PROXMOX_TOKEN contains a user different from PROXMOX_USER."
            )
        return f"PVEAPIToken={token_user}!{token_value}"
    return f"PVEAPIToken={normalized_user}!{normalized}"


def percent(value: Any) -> float | None:
    """Convert the Proxmox CPU fraction to a percentage."""
    try:
        return round(float(value or 0) * 100, 2)
    except (TypeError, ValueError):
        return None


def memory_percent(used: Any, maximum: Any) -> float | None:
    """Calculates memory percentage without failing on incomplete data."""
    try:
        if maximum is None or float(maximum) <= 0:
            return None
        return round(float(used or 0) / float(maximum) * 100, 2)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def parse_ip(value: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    """Valida un destino como IP literal, no como hostname arbitrario."""
    try:
        return ipaddress.ip_address(value.strip())
    except ValueError as exc:
        raise ValueError(f"Invalid target: {value!r}; an IP address is required.") from exc


def is_public_ip(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Return whether an IP is publicly routable."""
    return not (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    )


class ProxmoxClient:
    """Read-only client for the endpoints used by the scanner."""

    def __init__(
        self, host: str, user: str, token: str, port: str = "8006", verify_ssl: bool = False
    ) -> None:
        self.base_url = proxmox_base_url(host, port)
        self.session = requests.Session()
        self.session.verify = verify_ssl
        self.session.headers.update(
            {
                "Accept": "application/json",
                "Authorization": proxmox_auth_header(user, token),
            }
        )

    def get(self, path: str, *, optional: bool = False) -> Any:
        """Get ``data`` from Proxmox and distinguish optional failures."""
        url = f"{self.base_url}/{path.lstrip('/')}"
        try:
            response = self.session.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
            response.raise_for_status()
            payload = response.json()
        except requests.Timeout as exc:
            message = f"Timeout consultando Proxmox ({path})"
            if optional:
                raise OptionalEndpointError(message) from exc
            raise ProxmoxAPIError(message) from exc
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "unknown"
            message = f"HTTP {status} consultando Proxmox ({path})"
            if status == 401:
                message += "; revisa PROXMOX_USER y PROXMOX_TOKEN"
            if exc.response is not None:
                try:
                    error_payload = exc.response.json()
                    detail = error_payload.get("errors") or error_payload.get("message")
                    if detail:
                        message += f": {detail}"
                except ValueError:
                    pass
            if optional:
                raise OptionalEndpointError(message) from exc
            raise ProxmoxAPIError(message) from exc
        except requests.RequestException as exc:
            message = f"Error de red consultando Proxmox ({path}): {exc}"
            if optional:
                raise OptionalEndpointError(message) from exc
            raise ProxmoxAPIError(message) from exc
        except ValueError as exc:
            message = f"Invalid JSON returned by Proxmox ({path})"
            if optional:
                raise OptionalEndpointError(message) from exc
            raise ProxmoxAPIError(message) from exc

        if not isinstance(payload, dict) or "data" not in payload:
            message = f"Respuesta inesperada de Proxmox ({path})"
            if optional:
                raise OptionalEndpointError(message)
            raise ProxmoxAPIError(message)
        return payload["data"]

    def post(self, path: str, data: dict[str, Any]) -> Any:
        """Send a mutating operation only after menu confirmation."""
        url = f"{self.base_url}/{path.lstrip('/')}"
        try:
            response = self.session.post(
                url, data=data, timeout=REQUEST_TIMEOUT_SECONDS
            )
            response.raise_for_status()
            payload = response.json()
        except requests.Timeout as exc:
            raise ProxmoxAPIError(f"Timeout ejecutando Proxmox ({path})") from exc
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "unknown"
            message = f"HTTP {status} ejecutando Proxmox ({path})"
            if status == 401:
                message += "; revisa permisos del token"
            if exc.response is not None:
                try:
                    error_payload = exc.response.json()
                    detail = error_payload.get("errors") or error_payload.get("message")
                    if detail:
                        message += f": {detail}"
                except ValueError:
                    pass
            raise ProxmoxAPIError(message) from exc
        except requests.RequestException as exc:
            raise ProxmoxAPIError(f"Error de red ejecutando Proxmox ({path}): {exc}") from exc
        except ValueError as exc:
            raise ProxmoxAPIError(f"Invalid Proxmox JSON ({path})") from exc

        if not isinstance(payload, dict) or "data" not in payload:
            raise ProxmoxAPIError(f"Respuesta inesperada de Proxmox ({path})")
        return payload["data"]

    def create_vm(
        self,
        node: str,
        vmid: int,
        name: str,
        cores: int,
        memory: int,
        disk: str,
        iso: str,
        storage: str,
        bridge: str,
        ostype: str,
    ) -> Any:
        """Request creation of a QEMU VM with reviewed parameters."""
        data: dict[str, Any] = {
            "name": name,
            "cores": cores,
            "memory": memory,
            "scsi0": disk,
            "ide2": f"{iso},media=cdrom",
            "boot": "order=scsi0;ide2",
            "net0": f"virtio,bridge={bridge}",
            "scsihw": "virtio-scsi-pci",
            "ostype": ostype,
            "agent": "enabled=1",
            "onboot": 0,
        }
        data["vmid"] = vmid
        return self.post(f"/nodes/{quote(node, safe='')}/qemu", data)

    def next_vmid(self) -> int:
        """Solicita a Proxmox un VMID libre para evitar creaciones ambiguas."""
        data = self.get("/cluster/nextid")
        try:
            return int(data)
        except (TypeError, ValueError) as exc:
            raise ProxmoxAPIError(f"Proxmox returned an invalid VMID: {data!r}") from exc

    def node_storages(self, node: str) -> list[dict[str, Any]]:
        """Get active storage entries and their declared content."""
        data = self.get(f"/nodes/{quote(node, safe='')}/storage")
        if not isinstance(data, list):
            raise ProxmoxAPIError(f"Node {node} did not return valid storage entries.")
        return [item for item in data if isinstance(item, dict)]

    def nodes(self) -> list[dict[str, Any]]:
        """Get the available cluster nodes."""
        data = self.get("/nodes")
        if not isinstance(data, list):
            raise ProxmoxAPIError("The API did not return a valid node list.")
        return [item for item in data if isinstance(item, dict) and item.get("node")]

    def iso_images(self, node: str, storage: str) -> list[dict[str, Any]]:
        """Get and filter ISO images from storage."""
        path = (
            f"/nodes/{quote(node, safe='')}/storage/{quote(storage, safe='')}/content"
        )
        data = self.get(path, optional=True)
        if not isinstance(data, list):
            return []
        return [
            item for item in data
            if isinstance(item, dict)
            and (
                item.get("format") == "iso"
                or str(item.get("volid", "")).startswith(f"{storage}:iso/")
            )
        ]

    def shutdown(self, item: dict[str, Any]) -> Any:
        """Stop by type: ``stop`` for QEMU and ``shutdown`` for LXC."""
        action = "stop" if item["type"] == "VM" else "shutdown"
        return self.power_action(item, action)

    def power_action(self, item: dict[str, Any], action: str) -> Any:
        """Execute an allowed power action on a VM or LXC."""
        if action not in {"start", "shutdown", "stop"}:
            raise ValueError(f"Power action not allowed: {action}")
        guest_type = "qemu" if item["type"] == "VM" else "lxc"
        path = (
            f"/nodes/{quote(str(item['node']), safe='')}/{guest_type}/"
            f"{int(item['vmid'])}/status/{action}"
        )
        data = {"timeout": 60} if action == "shutdown" else {}
        return self.post(path, data)

    def current_status(self, item: dict[str, Any]) -> str:
        """Query the current state of a VM or container."""
        guest_type = "qemu" if item["type"] == "VM" else "lxc"
        path = (
            f"/nodes/{quote(str(item['node']), safe='')}/{guest_type}/"
            f"{int(item['vmid'])}/status/current"
        )
        data = self.get(path)
        if not isinstance(data, dict) or not isinstance(data.get("status"), str):
            raise ProxmoxAPIError(
                f"Proxmox did not return a valid state for {item['type']} {item['vmid']}."
            )
        return data["status"]

    def wait_for_status(
        self, item: dict[str, Any], expected: str, timeout: int = 60
    ) -> bool:
        """Espera hasta que Proxmox confirme el estado esperado."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.current_status(item) == expected:
                return True
            time.sleep(3)
        return self.current_status(item) == expected

    def inventory(self) -> list[dict[str, Any]]:
        """Lists nodes, QEMU VMs, and LXC containers."""
        nodes = self.get("/nodes")
        if not isinstance(nodes, list):
            raise ProxmoxAPIError("The API did not return a node list.")

        inventory: list[dict[str, Any]] = []
        for node_data in nodes:
            if not isinstance(node_data, dict) or not node_data.get("node"):
                LOGGER.warning("Node skipped because of invalid format: %r", node_data)
                continue
            node = str(node_data["node"])
            node_path = quote(node, safe="")
            for guest_type, label in (("qemu", "VM"), ("lxc", "LXC")):
                try:
                    guests = self.get(f"/nodes/{node_path}/{guest_type}")
                except ProxmoxAPIError as exc:
                    LOGGER.warning("Could not list %s en %s: %s", label, node, exc)
                    continue
                if not isinstance(guests, list):
                    LOGGER.warning("Invalid %s response on node %s.", label, node)
                    continue
                for guest in guests:
                    item = self._guest(node, node_path, guest_type, label, guest)
                    if item:
                        inventory.append(item)
        return inventory

    def _guest(
        self,
        node: str,
        node_path: str,
        guest_type: str,
        label: str,
        guest: Any,
    ) -> dict[str, Any] | None:
        """Build a resource and continue if an optional endpoint fails."""
        if not isinstance(guest, dict) or "vmid" not in guest:
            LOGGER.warning("%s skipped because of invalid format on %s.", label, node)
            return None
        try:
            vmid = int(guest["vmid"])
        except (TypeError, ValueError):
            LOGGER.warning("%s has an invalid VMID on %s.", label, node)
            return None

        path_prefix = f"/nodes/{node_path}/{guest_type}/{vmid}"
        config = self._optional_dict(f"{path_prefix}/config", label, vmid)
        snapshots = self._optional_list(f"{path_prefix}/snapshot", label, vmid)
        network = self._network_config(config)
        ips: list[str] = []

        if guest_type == "qemu":
            ips = self._qemu_agent_ips(path_prefix, label, vmid)
        else:
            ips = self._lxc_ips(config, label, vmid)

        return {
            "type": label,
            "node": node,
            "vmid": vmid,
            "name": guest.get("name", f"{guest_type}-{vmid}"),
            "status": guest.get("status", "unknown"),
            "cpu_percent": percent(guest.get("cpu")),
            "memory_used_bytes": guest.get("mem"),
            "memory_max_bytes": guest.get("maxmem"),
            "memory_percent": memory_percent(guest.get("mem"), guest.get("maxmem")),
            "network_config": network,
            "gpu_configuration": _gpu_details({}, config),
            "ips": ips,
            "snapshots": [
                {
                    "name": snapshot.get("name"),
                    "description": snapshot.get("description", ""),
                    "snaptime": snapshot.get("snaptime"),
                    "parent": snapshot.get("parent"),
                    "status": snapshot.get("status", "active"),
                }
                for snapshot in snapshots
                if isinstance(snapshot, dict)
                and str(snapshot.get("name", "")).lower() != "current"
            ],
        }

    def _optional_dict(self, path: str, label: str, vmid: int) -> dict[str, Any]:
        try:
            value = self.get(path, optional=True)
        except OptionalEndpointError as exc:
            LOGGER.warning("%s %s: %s", label, vmid, exc)
            return {}
        return value if isinstance(value, dict) else {}

    def _optional_list(self, path: str, label: str, vmid: int) -> list[Any]:
        try:
            value = self.get(path, optional=True)
        except OptionalEndpointError as exc:
            LOGGER.warning("%s %s: snapshots not available: %s", label, vmid, exc)
            return []
        return value if isinstance(value, list) else []

    @staticmethod
    def _network_config(config: dict[str, Any]) -> dict[str, Any]:
        """Extract netX entries from the resource configuration."""
        return {
            key: value
            for key, value in config.items()
            if key.startswith("net") and isinstance(value, str)
        }

    def _qemu_agent_ips(self, path_prefix: str, label: str, vmid: int) -> list[str]:
        """Query QEMU Guest Agent interfaces when enabled."""
        try:
            data = self.get(f"{path_prefix}/agent/network-get-interfaces", optional=True)
        except OptionalEndpointError as exc:
            LOGGER.debug("%s %s: QEMU Guest Agent not available: %s", label, vmid, exc)
            return []
        if not isinstance(data, dict):
            return []
        result = data.get("result", [])
        return self._ips_from_interfaces(result)

    @staticmethod
    def _lxc_ips(config: dict[str, Any], label: str, vmid: int) -> list[str]:
        """Extract IPs declared in netX; configuration does not guarantee more."""
        interfaces: list[dict[str, Any]] = []
        for key, value in config.items():
            if not key.startswith("net") or not isinstance(value, str):
                continue
            fields = dict(
                part.split("=", 1)
                for part in value.split(",")
                if "=" in part
            )
            if fields.get("ip"):
                interfaces.append({"ip-addresses": [{"ip-address": fields["ip"].split("/")[0]}]})
            if fields.get("ip6"):
                interfaces.append({"ip-addresses": [{"ip-address": fields["ip6"].split("/")[0]}]})
        return ProxmoxClient._ips_from_interfaces(interfaces)

    @staticmethod
    def _ips_from_interfaces(interfaces: Any) -> list[str]:
        """Normaliza estructuras de interfaces del Guest Agent o LXC."""
        ips: list[str] = []
        if not isinstance(interfaces, list):
            return ips
        for interface in interfaces:
            if not isinstance(interface, dict):
                continue
            addresses = interface.get("ip-addresses", [])
            if not isinstance(addresses, list):
                continue
            for address in addresses:
                if not isinstance(address, dict):
                    continue
                value = address.get("ip-address")
                if isinstance(value, str):
                    try:
                        parse_ip(value)
                    except ValueError:
                        continue
                    if value not in ips:
                        ips.append(value)
        return ips


def save_inventory(inventory: list[dict[str, Any]], output: str) -> None:
    """Save the inventory with readable encoding and stable formatting."""
    Path(output).write_text(
        json.dumps(inventory, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    LOGGER.info("Inventory saved to %s", output)


def _display_number(value: Any, suffix: str = "") -> str:
    """Formats optional values for the interface without hiding missing data."""
    return "not available" if value is None else f"{value}{suffix}"


def _format_bytes(value: Any) -> str:
    """Converts bytes to a human-readable terminal table unit."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "not available"
    if number < 1024:
        return f"{number:.0f} B"
    units = ("KB", "MB", "GB", "TB")
    for unit in units:
        number /= 1024
        if number < 1024 or unit == units[-1]:
            return f"{number:.1f} {unit}"
    return "not available"


def _format_memory(item: dict[str, Any]) -> str:
    """Display used/maximum memory and percentage in one column."""
    used = _format_bytes(item.get("memory_used_bytes"))
    maximum = _format_bytes(item.get("memory_max_bytes"))
    percentage = _display_number(item.get("memory_percent"), "%")
    if used == "not available" and maximum == "not available":
        return "not available"
    return f"{used}/{maximum} ({percentage})"


def _print_resource_section(title: str, resources: list[dict[str, Any]]) -> None:
    """Print a table section with calculated widths to avoid truncation."""
    if not resources:
        return
    columns = (
        ("VMID", lambda item: str(item.get("vmid", ""))),
        ("NAME", lambda item: str(item.get("name", ""))),
        ("NODE", lambda item: str(item.get("node", ""))),
        ("STATUS", lambda item: str(item.get("status", "unknown"))),
        ("CPU", lambda item: _display_number(item.get("cpu_percent"), "%")),
        ("USED/MAX MEMORY", _format_memory),
        ("IPS", lambda item: ", ".join(item.get("ips", [])) or "-"),
        ("SNAPSHOTS", lambda item: str(len(item.get("snapshots", [])))),
    )
    rows = [[formatter(item) for _, formatter in columns] for item in resources]
    widths = [
        max(len(header), *(len(row[index]) for row in rows))
        for index, (header, _) in enumerate(columns)
    ]
    separator = "-+-".join("-" * width for width in widths)
    header = " | ".join(
        header.ljust(width) for (header, _), width in zip(columns, widths)
    )
    print(f"\n{title} ({len(resources)})")
    print(separator)
    print(header)
    print(separator)
    for row in rows:
        print(" | ".join(value.ljust(width) for value, width in zip(row, widths)))
    print(separator)


def _gpu_details(network_config: dict[str, Any], config: dict[str, Any] | None = None) -> list[str]:
    """Extract GPU passthrough or virtual GPU hints from configuration."""
    values = list(network_config.values())
    if config:
        values.extend(str(value) for value in config.values())
    return [
        value
        for value in values
        if any(marker in value.lower() for marker in ("hostpci", "gpu", "mdev", "vga="))
    ]


def _print_resource_table(inventory: list[dict[str, Any]]) -> None:
    """Display VMs and LXC containers in separate readable tables."""
    if not inventory:
        print("There are no VMs or containers in the inventory.")
        return
    print("\n" + "=" * 120)
    print("PROXMOX INVENTORY")
    print("Memory: used/maximum (percentage). IPs and snapshots are shown when available.")
    print("=" * 120)
    _print_resource_section("QEMU VIRTUAL MACHINES", [
        item for item in inventory if item.get("type") == "VM"
    ])
    _print_resource_section("LXC CONTAINERS", [
        item for item in inventory if item.get("type") == "LXC"
    ])


def _find_resource(inventory: list[dict[str, Any]], vmid_text: str) -> dict[str, Any] | None:
    """Finds a resource by VMID and rejects ambiguous selections."""
    try:
        vmid = int(vmid_text)
    except ValueError:
        return None
    matches = [item for item in inventory if item.get("vmid") == vmid]
    return matches[0] if len(matches) == 1 else None


def _print_resource_detail(item: dict[str, Any]) -> None:
    """Display resource usage, networking, IPs, snapshots, and GPU hints."""
    print(json.dumps(item, ensure_ascii=False, indent=2))
    print("\nConsumo actual:")
    print(f"  CPU: {_display_number(item.get('cpu_percent'), '%')}")
    print(f"  Memory used: {_display_number(item.get('memory_used_bytes'), ' bytes')}")
    print(f"  Maximum memory: {_display_number(item.get('memory_max_bytes'), ' bytes')}")
    print(f"  Memory usage: {_display_number(item.get('memory_percent'), '%')}")
    print("  GPU: inventory does not measure instantaneous GPU usage through the standard API.")
    gpu = item.get("gpu_configuration", [])
    print("       GPU/passthrough configuration: " + (", ".join(gpu) or "not configured"))
    print("  IPs: " + (", ".join(item.get("ips", [])) or "not available"))
    print("  Snapshots: " + (str(len(item.get("snapshots", []))) or "0"))


def _shutdown_resource(
    client: ProxmoxClient, inventory: list[dict[str, Any]], execute: bool
) -> None:
    """Stops using the command corresponding to the resource type."""
    item = _find_resource(inventory, input("VMID/LXCID: ").strip())
    if not item:
        print("No single resource was found for that VMID.")
        return
    status = client.current_status(item) if execute else item.get("status", "unknown")
    if status != "running":
        print(f"The resource is in {status} state; stop will not be prepared.")
        return
    command = "qm stop" if item["type"] == "VM" else "pct shutdown"
    print(f"\nRequested operation: {command} {item['vmid']}")
    if item["type"] == "VM":
        print("QEMU: stop will be sent according to the configured policy.")
    else:
        print("LXC: graceful shutdown will be sent.")
    if not execute:
        print("DRY-RUN: no changes were executed. Use --execute to enable them.")
        return
    if input("Type STOP to confirm: ").strip() != "STOP":
        print("Operation cancelled.")
        return
    result = client.shutdown(item)
    print(f"Stop requested. Proxmox task: {result}")
    if client.wait_for_status(item, "stopped", timeout=60):
        print("Proxmox confirmed that the resource is stopped.")
        return
    print("Could not confirm that the resource stopped after 60 seconds.")


def _start_resource(
    client: ProxmoxClient, inventory: list[dict[str, Any]], execute: bool
) -> None:
    """Starts a resource and verifies that it reaches the running state."""
    item = _find_resource(inventory, input("VMID/LXCID: ").strip())
    if not item:
        print("No single resource was found for that VMID.")
        return
    status = client.current_status(item) if execute else item.get("status", "unknown")
    if status == "running":
        print("The resource is already running.")
        return
    print(
        f"\nRequested operation: "
        f"{'qm' if item['type'] == 'VM' else 'pct'} start {item['vmid']}"
    )
    if not execute:
        print("DRY-RUN: no changes were executed. Use --execute to enable them.")
        return
    if input("Type START to confirm: ").strip() != "START":
        print("Operation cancelled.")
        return
    result = client.power_action(item, "start")
    print(f"Start requested. Proxmox task: {result}")
    if client.wait_for_status(item, "running", timeout=60):
        print("Proxmox confirmed that the resource is running.")
    else:
        print("Could not confirm the running state within 60 seconds.")


def _create_vm(client: ProxmoxClient, execute: bool) -> None:
    """Collect parameters and prepare or execute VM creation."""
    try:
        available_nodes = client.nodes()
    except ProxmoxAPIError as exc:
        print(f"Available nodes could not be retrieved: {exc}")
        return
    if not available_nodes:
        print("No nodes are available to create the VM.")
        return
    print("\nAvailable nodes:")
    for index, node_data in enumerate(available_nodes, 1):
        node_name = node_data.get("node")
        status = node_data.get("status", "unknown")
        cpu_count = node_data.get("maxcpu", "n/d")
        memory_free_value = node_data.get("memfree")
        if memory_free_value is None:
            try:
                memory_free_value = float(node_data["maxmem"]) - float(node_data["mem"])
            except (KeyError, TypeError, ValueError):
                memory_free_value = None
        memory_free = _format_bytes(memory_free_value)
        print(
            f"  {index}. {node_name} "
            f"(status: {status}, CPU: {cpu_count}, free memory: {memory_free})"
        )
    try:
        node_index = int(input("Select node [1]: ").strip() or "1")
        node = str(available_nodes[node_index - 1]["node"])
    except (ValueError, IndexError):
        print("Invalid node selection.")
        return

    name = input("VM name: ").strip()
    vmid = input("VMID (blank for automatic): ").strip()
    cores = input("CPU cores [2]: ").strip() or "2"
    memory = input("Memory in MB [2048]: ").strip() or "2048"
    if not node or not name:
        print("Node and name are required.")
        return

    try:
        storages = client.node_storages(node)
    except ProxmoxAPIError as exc:
        print(f"Node storage could not be retrieved: {exc}")
        return
    usable = [
        storage for storage in storages
        if storage.get("active") and storage.get("enabled", 1)
        and "images" in str(storage.get("content", "")).split(",")
    ]
    if not usable:
        print("No active storage enabled for VM disks was found.")
        return
    print("\nDisk storage:")
    for index, storage in enumerate(usable, 1):
        available = _format_bytes(storage.get("avail"))
        print(f"  {index}. {storage.get('storage')} ({storage.get('type')}, libre: {available})")
    try:
        storage_index = int(input("Select storage [1]: ").strip() or "1")
        selected_storage = usable[storage_index - 1]
    except (ValueError, IndexError):
        print("Invalid storage selection.")
        return
    storage_name = str(selected_storage["storage"])

    iso_storages = [
        storage for storage in storages
        if storage.get("active") and storage.get("enabled", 1)
        and "iso" in str(storage.get("content", "")).split(",")
    ]
    iso_options: list[tuple[str, str]] = []
    for iso_storage in iso_storages:
        iso_name = str(iso_storage["storage"])
        try:
            for iso in client.iso_images(node, iso_name):
                volid = iso.get("volid")
                if isinstance(volid, str):
                    iso_options.append((iso_name, volid))
        except (OptionalEndpointError, ProxmoxAPIError) as exc:
            LOGGER.warning("Could not list ISOs from %s: %s", iso_name, exc)
    if not iso_options:
        print("No ISO images were found in node storage.")
        return
    print("\nAvailable ISO images:")
    for index, (_, volid) in enumerate(iso_options, 1):
        print(f"  {index}. {volid}")
    try:
        iso_index = int(input("Select ISO [1]: ").strip() or "1")
        _, iso = iso_options[iso_index - 1]
    except (ValueError, IndexError):
        print("Invalid ISO selection.")
        return

    default_ostype = "win11" if any(
        marker in iso.lower() for marker in ("win10", "win11", "windows")
    ) else "l26"
    ostype = (
        input(f"Operating system type [l26/linux, win11/windows] [{default_ostype}]: ")
        .strip()
        or default_ostype
    )
    if ostype not in {"l26", "win10", "win11", "other"}:
        print("Invalid operating system type. Use l26, win10, win11, or other.")
        return
    disk_size = input("Disk size in GB [32]: ").strip() or "32"
    bridge = input("Network bridge [vmbr0]: ").strip() or "vmbr0"
    try:
        selected_vmid = int(vmid) if vmid else client.next_vmid()
        if selected_vmid <= 0:
            raise ValueError
        if int(cores) <= 0 or int(memory) <= 0 or int(disk_size) <= 0:
            raise ValueError
    except ValueError:
        print("VMID, CPU, memory, and disk must be valid numeric values.")
        return
    except ProxmoxAPIError as exc:
        print(f"A free VMID could not be obtained: {exc}")
        return
    disk = f"{storage_name}:{disk_size}"
    command = ["qm", "create", str(selected_vmid), "--name", name,
               "--cores", cores, "--memory", memory, "--scsi0", disk,
               "--ide2", f"{iso},media=cdrom", "--boot", "order=scsi0;ide2",
               "--net0", f"virtio,bridge={bridge}", "--scsihw", "virtio-scsi-pci",
               "--ostype", ostype, "--agent", "enabled=1"]
    print("\nReviewed parameters:")
    print(f"Selected node: {node}")
    print(f"Assigned VMID: {selected_vmid}")
    print(f"Disk storage: {storage_name}")
    print(f"Installation ISO: {iso}")
    print(f"Operating system type: {ostype}")
    print(f"Network bridge: {bridge}")
    print("Command that would be executed: " + " ".join(command))
    if not execute:
        print("DRY-RUN: no changes were executed. Use --execute to enable them.")
        return
    if input("Type CREATE to confirm: ").strip() != "CREATE":
        print("Operation cancelled.")
        return
    result = client.create_vm(
        node,
        selected_vmid,
        name,
        int(cores),
        int(memory),
        disk,
        iso,
        storage_name,
        bridge,
        ostype,
    )
    print(f"Creation requested. Proxmox task: {result}")


def interactive_interface(
    client: ProxmoxClient,
    inventory: list[dict[str, Any]],
    output: str,
    execute: bool,
) -> None:
    """Interactive menu for queries and safe operation preparation."""
    current = inventory
    while True:
        print(
            "\n" + "=" * 72
            + f"\nPROXMOX INTERFACE ({'REAL EXECUTION' if execute else 'DRY-RUN'})\n"
            "1. List VMs and containers\n"
            "2. View resource usage and details\n"
            "3. Refresh inventory\n"
            "4. Create VM\n"
            "5. Stop VM/LXC\n"
            "6. Start VM/LXC\n"
            "7. Save inventory\n"
            "0. Exit\n"
            + "=" * 72
        )
        option = input("Select an option: ").strip()
        if option == "1":
            _print_resource_table(current)
        elif option == "2":
            item = _find_resource(current, input("VMID/LXCID: ").strip())
            if item:
                _print_resource_detail(item)
            else:
                print("No single resource was found for that VMID.")
        elif option == "3":
            try:
                current = client.inventory()
            except ProxmoxAPIError as exc:
                print(f"Inventory refresh failed: {exc}")
            else:
                save_inventory(current, output)
                print(f"Inventory refreshed: {len(current)} resources.")
        elif option == "4":
            _create_vm(client, execute)
        elif option == "5":
            _shutdown_resource(client, current, execute)
        elif option == "6":
            _start_resource(client, current, execute)
        elif option == "7":
            save_inventory(current, output)
        elif option == "0":
            return
        else:
            print("Invalid option.")


def nmap_scan(targets: list[str], allow_public: bool) -> None:
    """Runs Nmap with fixed, non-destructive arguments."""
    nmap_path = shutil.which("nmap")
    if not nmap_path:
        raise RuntimeError("Nmap is not installed or is unavailable in PATH.")
    validated: list[str] = []
    for target in targets:
        address = parse_ip(target)
        if is_public_ip(address) and not allow_public:
            raise ValueError(
                f"Public IP {target} was rejected; use --allow-public explicitly."
            )
        normalized = str(address)
        if normalized not in validated:
            validated.append(normalized)
    if not validated:
        LOGGER.info("There are no valid IPs to scan.")
        return

    command = [nmap_path, "-sV", "-Pn", "--top-ports", "100", "-T3", "--open"]
    command.extend(validated)
    LOGGER.info("Running Nmap against %d target(s).", len(validated))
    try:
        subprocess.run(command, check=True, timeout=900)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Nmap exceeded the 900-second timeout.") from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"Nmap exited with code {exc.returncode}.") from exc


def gemini_client(api_key: str) -> tuple[Any, str]:
    """Load Gemini only when an AI feature is requested."""
    try:
        from google import genai
    except ImportError as exc:
        raise RuntimeError(
            "Gemini is not installed; run: python -m pip install google-genai"
        ) from exc
    return genai.Client(api_key=api_key), os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)


def gemini_request(operation: Callable[[], T]) -> T:
    """Reintenta fallos transitorios del servicio Gemini."""
    try:
        from google.genai import errors as genai_errors
    except ImportError:
        return operation()
    for attempt in range(GEMINI_MAX_RETRIES + 1):
        try:
            return operation()
        except genai_errors.APIError as exc:
            code = getattr(exc, "code", None)
            retryable = code in {429, 500, 502, 503, 504} or any(
                marker in str(exc).upper()
                for marker in ("429", "500", "502", "503", "504", "UNAVAILABLE")
            )
            if not retryable or attempt >= GEMINI_MAX_RETRIES:
                raise RuntimeError(f"Error de la API de Gemini: {exc}") from exc
            delay = GEMINI_RETRY_DELAYS[attempt]
            LOGGER.warning("Gemini not available; reintento en %d s.", delay)
            time.sleep(delay)
    raise RuntimeError("Gemini finished without a response.")


def ai_report(inventory: list[dict[str, Any]], api_key: str) -> str:
    """Generates a defensive report without executing actions."""
    client, model = gemini_client(api_key)
    prompt = f"""Analyze this authorized Proxmox VE inventory in English:
{json.dumps(inventory, ensure_ascii=False, indent=2)}

Include a summary, recursos inactivos, snapshots antiguos, IPs descubiertas,
risks and a prioritized plan. Suggest diagnostic or remediation commands,
but do not execute or claim to have executed changes. Do not invent
datos y distingue siempre type=VM de type=LXC."""
    response = gemini_request(
        lambda: client.models.generate_content(model=model, contents=prompt)
    )
    text = getattr(response, "text", None)
    if not text or not text.strip():
        raise RuntimeError("Gemini returned an empty report.")
    return text.strip()


def chat(inventory: list[dict[str, Any]], api_key: str) -> None:
    """Open an optional interactive session based on the inventory."""
    client, model = gemini_client(api_key)
    session = client.chats.create(model=model)
    context = (
        "Always respond in English and use only this authorized inventory. "
        "No ejecutes cambios ni inventes datos:\n"
        + json.dumps(inventory, ensure_ascii=False, indent=2)
    )
    gemini_request(lambda: session.send_message(context))
    print("\nINTERACTIVE CHAT (type exit to quit)")
    while True:
        try:
            question = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nSession ended.")
            return
        if question.lower() in {"exit", "exit", "quit"}:
            print("Session ended.")
            return
        if not question:
            continue
        try:
            response = gemini_request(lambda: session.send_message(question))
        except RuntimeError as exc:
            LOGGER.error("Gemini no pudo responder: %s", exc)
            continue
        text = getattr(response, "text", None)
        if text:
            print(f"\nGemini:\n{text.strip()}")


def arguments(argv: list[str] | None = None) -> argparse.Namespace:
    """Define the command-line interface."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nmap", action="store_true", help="Scan discovered IPs.")
    parser.add_argument("--target", action="append", default=[], help="Additional IP; may be repeated.")
    parser.add_argument("--allow-public", action="store_true", help="Explicitly allow public IPs.")
    parser.add_argument("--ai", action="store_true", help="Generate a Gemini report.")
    parser.add_argument("--chat", action="store_true", help="Open an interactive Gemini chat.")
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Open the interactive query and operations menu.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Allow real creation and power operations; confirmation is required.",
    )
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help=f"Output JSON file (default: {DEFAULT_OUTPUT}).")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Run inventory, persistence, Nmap, and AI according to the selected options."""
    load_dotenv()
    args = arguments(argv)
    try:
        client = ProxmoxClient(
            required_env("PROXMOX_HOST"),
            required_env("PROXMOX_USER"),
            required_env("PROXMOX_TOKEN"),
            optional_env("PROXMOX_PORT", "8006"),
            env_bool("PROXMOX_VERIFY_SSL", False),
        )
        if args.execute and not args.interactive:
            raise ValueError("--execute requires --interactive.")

        LOGGER.info("Querying Proxmox VE inventory...")
        try:
            inventory = client.inventory()
        except ProxmoxAPIError as exc:
            if not args.interactive:
                raise
            inventory = []
            LOGGER.error("Initial inventory query failed: %s", exc)
            print("\nThe interactive menu is available, but the inventory could not be loaded.")
            print("Use option 3 to retry after correcting the Proxmox credentials or permissions.")
        else:
            save_inventory(inventory, args.output)
            vm_count = sum(item["type"] == "VM" for item in inventory)
            lxc_count = sum(item["type"] == "LXC" for item in inventory)
            print(f"Resources found: {len(inventory)} (VMs: {vm_count}, LXC: {lxc_count})")

        if args.interactive:
            interactive_interface(client, inventory, args.output, args.execute)
            return 0

        discovered = [ip for item in inventory for ip in item["ips"]]

        if args.nmap:
            nmap_scan(discovered + args.target, args.allow_public)
        elif args.target:
            LOGGER.warning("--target is only executed together with --nmap.")

        if args.ai or args.chat:
            api_key = required_env("GOOGLE_API_KEY")
            if args.ai:
                print("\n" + "=" * 80 + "\nGEMINI REPORT\n" + "=" * 80)
                print(ai_report(inventory, api_key))
            if args.chat:
                chat(inventory, api_key)
        return 0
    except (ValueError, ProxmoxAPIError, RuntimeError, OSError) as exc:
        LOGGER.error("%s", exc)
        return 1


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    sys.exit(main())
