"""Inventario defensivo de VMs QEMU y contenedores LXC en Proxmox VE.

El programa solo realiza consultas de lectura contra Proxmox y, si se solicita,
escaneos Nmap de IPs autorizadas. Nunca apaga, elimina, modifica ni reinicia
recursos.
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
from urllib.parse import quote

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

# Los certificados autofirmados son habituales en redes de administración.
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class ProxmoxAPIError(RuntimeError):
    """Error fatal al consultar la API principal de Proxmox."""


class OptionalEndpointError(RuntimeError):
    """Error de un endpoint cuyo fallo no debe abortar el inventario."""


def required_env(name: str) -> str:
    """Obtiene una variable obligatoria sin revelar su contenido en logs."""
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"Falta la variable de entorno obligatoria: {name}")
    return value


def proxmox_base_url(host: str) -> str:
    """Normaliza un host, URL o URL de API de Proxmox."""
    normalized = host.strip().rstrip("/")
    if not normalized.startswith(("http://", "https://")):
        normalized = f"https://{normalized}:8006"
    for suffix in ("/api2/json", "/api2/extjs", "/api2/html"):
        if normalized.endswith(suffix):
            normalized = normalized[: -len(suffix)]
            break
    return f"{normalized}/api2/json"


def proxmox_auth_header(user: str, token: str) -> str:
    """Acepta TOKEN_ID=SECRET, usuario!TOKEN_ID=SECRET o header completo."""
    normalized = token.strip()
    if normalized.startswith("PVEAPIToken="):
        normalized = normalized[len("PVEAPIToken=") :]

    if "!" in normalized:
        token_user, token_value = normalized.split("!", 1)
        if token_user != user:
            raise ValueError(
                "PROXMOX_TOKEN contiene un usuario distinto de PROXMOX_USER."
            )
        return f"PVEAPIToken={token_user}!{token_value}"
    return f"PVEAPIToken={user}!{normalized}"


def percent(value: Any) -> float | None:
    """Convierte la fracción de CPU de Proxmox a porcentaje."""
    try:
        return round(float(value or 0) * 100, 2)
    except (TypeError, ValueError):
        return None


def memory_percent(used: Any, maximum: Any) -> float | None:
    """Calcula el porcentaje de memoria sin fallar por datos incompletos."""
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
        raise ValueError(f"Destino no válido: {value!r}; debe ser una dirección IP.") from exc


def is_public_ip(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Indica si una IP es enrutable públicamente."""
    return not (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    )


class ProxmoxClient:
    """Cliente de solo lectura para los endpoints usados por el escáner."""

    def __init__(self, host: str, user: str, token: str) -> None:
        self.base_url = proxmox_base_url(host)
        self.session = requests.Session()
        self.session.verify = False
        self.session.headers.update(
            {
                "Accept": "application/json",
                "Authorization": proxmox_auth_header(user, token),
            }
        )

    def get(self, path: str, *, optional: bool = False) -> Any:
        """Obtiene ``data`` de Proxmox y diferencia fallos opcionales."""
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
            status = exc.response.status_code if exc.response is not None else "desconocido"
            message = f"HTTP {status} consultando Proxmox ({path})"
            if status == 401:
                message += "; revisa PROXMOX_USER y PROXMOX_TOKEN"
            if optional:
                raise OptionalEndpointError(message) from exc
            raise ProxmoxAPIError(message) from exc
        except requests.RequestException as exc:
            message = f"Error de red consultando Proxmox ({path}): {exc}"
            if optional:
                raise OptionalEndpointError(message) from exc
            raise ProxmoxAPIError(message) from exc
        except ValueError as exc:
            message = f"JSON inválido devuelto por Proxmox ({path})"
            if optional:
                raise OptionalEndpointError(message) from exc
            raise ProxmoxAPIError(message) from exc

        if not isinstance(payload, dict) or "data" not in payload:
            message = f"Respuesta inesperada de Proxmox ({path})"
            if optional:
                raise OptionalEndpointError(message)
            raise ProxmoxAPIError(message)
        return payload["data"]

    def inventory(self) -> list[dict[str, Any]]:
        """Enumera nodos, VMs QEMU y contenedores LXC."""
        nodes = self.get("/nodes")
        if not isinstance(nodes, list):
            raise ProxmoxAPIError("La API no devolvió una lista de nodos.")

        inventory: list[dict[str, Any]] = []
        for node_data in nodes:
            if not isinstance(node_data, dict) or not node_data.get("node"):
                LOGGER.warning("Nodo omitido por formato inválido: %r", node_data)
                continue
            node = str(node_data["node"])
            node_path = quote(node, safe="")
            for guest_type, label in (("qemu", "VM"), ("lxc", "LXC")):
                try:
                    guests = self.get(f"/nodes/{node_path}/{guest_type}")
                except ProxmoxAPIError as exc:
                    LOGGER.warning("No se pudo listar %s en %s: %s", label, node, exc)
                    continue
                if not isinstance(guests, list):
                    LOGGER.warning("Respuesta inválida de %s en el nodo %s.", label, node)
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
        """Construye un recurso y continúa si falla un endpoint opcional."""
        if not isinstance(guest, dict) or "vmid" not in guest:
            LOGGER.warning("%s omitido por formato inválido en %s.", label, node)
            return None
        try:
            vmid = int(guest["vmid"])
        except (TypeError, ValueError):
            LOGGER.warning("%s con VMID inválido en %s.", label, node)
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
            LOGGER.warning("%s %s: snapshots no disponibles: %s", label, vmid, exc)
            return []
        return value if isinstance(value, list) else []

    @staticmethod
    def _network_config(config: dict[str, Any]) -> dict[str, Any]:
        """Extrae las entradas netX de la configuración del recurso."""
        return {
            key: value
            for key, value in config.items()
            if key.startswith("net") and isinstance(value, str)
        }

    def _qemu_agent_ips(self, path_prefix: str, label: str, vmid: int) -> list[str]:
        """Consulta interfaces del QEMU Guest Agent si está habilitado."""
        try:
            data = self.get(f"{path_prefix}/agent/network-get-interfaces", optional=True)
        except OptionalEndpointError as exc:
            LOGGER.warning("%s %s: QEMU Guest Agent no disponible: %s", label, vmid, exc)
            return []
        if not isinstance(data, dict):
            return []
        result = data.get("result", [])
        return self._ips_from_interfaces(result)

    @staticmethod
    def _lxc_ips(config: dict[str, Any], label: str, vmid: int) -> list[str]:
        """Extrae IPs declaradas en netX; la API de configuración no garantiza más."""
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
    """Guarda el inventario con codificación legible y formato estable."""
    Path(output).write_text(
        json.dumps(inventory, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    LOGGER.info("Inventario guardado en %s", output)


def nmap_scan(targets: list[str], allow_public: bool) -> None:
    """Ejecuta Nmap con argumentos fijos y no destructivos."""
    nmap_path = shutil.which("nmap")
    if not nmap_path:
        raise RuntimeError("Nmap no está instalado o no está disponible en PATH.")
    validated: list[str] = []
    for target in targets:
        address = parse_ip(target)
        if is_public_ip(address) and not allow_public:
            raise ValueError(
                f"Se rechazó la IP pública {target}; usa --allow-public explícitamente."
            )
        normalized = str(address)
        if normalized not in validated:
            validated.append(normalized)
    if not validated:
        LOGGER.info("No hay IPs válidas para escanear.")
        return

    command = [nmap_path, "-sV", "-Pn", "--top-ports", "100", "-T3", "--open"]
    command.extend(validated)
    LOGGER.info("Ejecutando Nmap sobre %d destino(s).", len(validated))
    try:
        subprocess.run(command, check=True, timeout=900)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Nmap superó el timeout de 900 segundos.") from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"Nmap terminó con código {exc.returncode}.") from exc


def gemini_client(api_key: str) -> tuple[Any, str]:
    """Carga Gemini solo cuando se solicita una función de IA."""
    try:
        from google import genai
    except ImportError as exc:
        raise RuntimeError(
            "Gemini no está instalado; ejecuta: python -m pip install google-genai"
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
            LOGGER.warning("Gemini no disponible; reintento en %d s.", delay)
            time.sleep(delay)
    raise RuntimeError("Gemini terminó sin respuesta.")


def ai_report(inventory: list[dict[str, Any]], api_key: str) -> str:
    """Genera un informe defensivo sin ejecutar acciones."""
    client, model = gemini_client(api_key)
    prompt = f"""Analiza en español este inventario autorizado de Proxmox VE:
{json.dumps(inventory, ensure_ascii=False, indent=2)}

Incluye resumen, recursos inactivos, snapshots antiguos, IPs descubiertas,
riesgos operativos y un plan priorizado. Propón comandos de diagnóstico o
remediación, pero no ejecutes ni afirmes haber ejecutado cambios. No inventes
datos y distingue siempre type=VM de type=LXC."""
    response = gemini_request(
        lambda: client.models.generate_content(model=model, contents=prompt)
    )
    text = getattr(response, "text", None)
    if not text or not text.strip():
        raise RuntimeError("Gemini devolvió un informe vacío.")
    return text.strip()


def chat(inventory: list[dict[str, Any]], api_key: str) -> None:
    """Abre una sesión interactiva opcional basada en el inventario."""
    client, model = gemini_client(api_key)
    session = client.chats.create(model=model)
    context = (
        "Responde siempre en español y usa solo este inventario autorizado. "
        "No ejecutes cambios ni inventes datos:\n"
        + json.dumps(inventory, ensure_ascii=False, indent=2)
    )
    gemini_request(lambda: session.send_message(context))
    print("\nCHAT INTERACTIVO (escribe salir para terminar)")
    while True:
        try:
            question = input("\nTú: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nSesión finalizada.")
            return
        if question.lower() in {"salir", "exit", "quit"}:
            print("Sesión finalizada.")
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
    """Define la interfaz de línea de comandos."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nmap", action="store_true", help="Escanear IPs descubiertas.")
    parser.add_argument("--target", action="append", default=[], help="IP adicional; se puede repetir.")
    parser.add_argument("--allow-public", action="store_true", help="Permitir IPs públicas explícitamente.")
    parser.add_argument("--ai", action="store_true", help="Generar informe con Gemini.")
    parser.add_argument("--chat", action="store_true", help="Abrir chat interactivo con Gemini.")
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help=f"Archivo JSON de salida (predeterminado: {DEFAULT_OUTPUT}).")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Ejecuta inventario, persistencia, Nmap e IA según las opciones."""
    load_dotenv()
    args = arguments(argv)
    try:
        client = ProxmoxClient(
            required_env("PROXMOX_HOST"),
            required_env("PROXMOX_USER"),
            required_env("PROXMOX_TOKEN"),
        )
        LOGGER.info("Consultando inventario de Proxmox VE...")
        inventory = client.inventory()
        save_inventory(inventory, args.output)
        discovered = [ip for item in inventory for ip in item["ips"]]
        vm_count = sum(item["type"] == "VM" for item in inventory)
        lxc_count = sum(item["type"] == "LXC" for item in inventory)
        print(f"Recursos encontrados: {len(inventory)} (VMs: {vm_count}, LXC: {lxc_count})")

        if args.nmap:
            nmap_scan(discovered + args.target, args.allow_public)
        elif args.target:
            LOGGER.warning("--target solo se ejecuta junto con --nmap.")

        if args.ai or args.chat:
            api_key = required_env("GOOGLE_API_KEY")
            if args.ai:
                print("\n" + "=" * 80 + "\nINFORME DE GEMINI\n" + "=" * 80)
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
