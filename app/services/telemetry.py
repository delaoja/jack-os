import time
from typing import Any, Dict

import psutil
import requests
import urllib3

from app.config import settings

# Disable TLS warnings for self-signed certificates on Proxmox
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class TelemetryCollector:
    """Collects system telemetry from Proxmox VE API or falls back to local psutil."""

    # Internal state for dynamic network throughput calculation
    last_net_time: float = 0.0
    last_bytes_in: int = 0
    last_bytes_out: int = 0

    @classmethod
    def get_proxmox_status(cls) -> Dict[str, Any] | None:
        if not settings.proxmox_token:
            return None

        url = (
            f"https://{settings.proxmox_host}:{settings.proxmox_port}"
            f"/api2/json/nodes/{settings.proxmox_node}/status"
        )
        headers = {
            "Authorization": f"PVEAPIToken={settings.proxmox_user}={settings.proxmox_token}"
        }

        try:
            resp = requests.get(
                url,
                headers=headers,
                verify=settings.proxmox_verify_ssl,
                timeout=5.0,
            )
            if resp.status_code == 200:
                return resp.json().get("data", {})
        except Exception:
            return None
        return None

    @classmethod
    def get_system_metrics(cls) -> Dict[str, Any]:
        pve_data = cls.get_proxmox_status()
        current_time = time.time()

        if pve_data:
            # 1. CPU Metrics
            cpu_usage = round(pve_data.get("cpu", 0.0) * 100, 2)
            cpu_info = pve_data.get("cpuinfo", {})
            cores_count = cpu_info.get("cores", 4)
            cpus_count = cpu_info.get("cpus", 8)

            # 2. Memory Metrics
            mem = pve_data.get("memory", {})
            total_mem = mem.get("total", 1)
            used_mem = mem.get("used", 0)
            free_mem = mem.get("free", 0)
            mem_pct = round((used_mem / total_mem) * 100, 2) if total_mem else 0.0

            # 3. Storage / Disk Metrics
            root_fs = pve_data.get("rootfs", {})
            total_disk = root_fs.get("total", 1)
            used_disk = root_fs.get("used", 0)
            free_disk = root_fs.get("free", 0)
            disk_pct = round((used_disk / total_disk) * 100, 2) if total_disk else 0.0

            # 4. Network Metrics (Fallback to active interface if PVE node status lacks net counters)
            bytes_in = pve_data.get("netin")
            bytes_out = pve_data.get("netout")

            if bytes_in is None or bytes_out is None:
                net_io = psutil.net_io_counters()
                bytes_in = net_io.bytes_recv
                bytes_out = net_io.bytes_sent

            time_delta = max(current_time - cls.last_net_time, 1.0) if cls.last_net_time else 1.0

            rx_rate_kb = (
                round(max(0, bytes_in - cls.last_bytes_in) / (1024 * time_delta), 2)
                if cls.last_net_time
                else 0.0
            )
            tx_rate_kb = (
                round(max(0, bytes_out - cls.last_bytes_out) / (1024 * time_delta), 2)
                if cls.last_net_time
                else 0.0
            )

            cls.last_net_time = current_time
            cls.last_bytes_in = bytes_in
            cls.last_bytes_out = bytes_out

            return {
                "timestamp": int(current_time),
                "source": "PROXMOX_VE_CORE",
                "node": settings.proxmox_node,
                "cpu": {
                    "percent": cpu_usage,
                    "logical_cores": cpus_count,
                    "cores": cores_count,
                },
                "memory": {
                    "percent": mem_pct,
                    "total_mb": round(total_mem / (1024 * 1024), 2),
                    "used_mb": round(used_mem / (1024 * 1024), 2),
                    "available_mb": round(free_mem / (1024 * 1024), 2),
                },
                "disk": {
                    "percent": disk_pct,
                    "total_gb": round(total_disk / (1024 * 1024 * 1024), 2),
                    "used_gb": round(used_disk / (1024 * 1024 * 1024), 2),
                    "free_gb": round(free_disk / (1024 * 1024 * 1024), 2),
                },
                "network": {
                    "bytes_sent": bytes_out,
                    "bytes_recv": bytes_in,
                    "bytes_received": bytes_in,
                    "packets_sent": int(bytes_out / 1200),
                    "packets_recv": int(bytes_in / 1200),
                    "rx_rate_kb_s": rx_rate_kb,
                    "tx_rate_kb_s": tx_rate_kb,
                },
            }

        # Fallback local metrics (psutil)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        net_io = psutil.net_io_counters()

        return {
            "timestamp": int(current_time),
            "source": "LOCAL_FALLBACK",
            "node": settings.node_id,
            "cpu": {
                "percent": psutil.cpu_percent(interval=None),
                "logical_cores": psutil.cpu_count(logical=True),
            },
            "memory": {
                "percent": memory.percent,
                "total_mb": round(memory.total / (1024 * 1024), 2),
                "used_mb": round(memory.used / (1024 * 1024), 2),
                "available_mb": round(memory.available / (1024 * 1024), 2),
            },
            "disk": {
                "percent": disk.percent,
                "total_gb": round(disk.total / (1024 * 1024 * 1024), 2),
                "used_gb": round(disk.used / (1024 * 1024 * 1024), 2),
                "free_gb": round(disk.free / (1024 * 1024 * 1024), 2),
            },
            "network": {
                "bytes_sent": net_io.bytes_sent,
                "bytes_recv": net_io.bytes_recv,
                "bytes_received": net_io.bytes_recv,
                "packets_sent": getattr(net_io, "packets_sent", 0),
                "packets_recv": getattr(net_io, "packets_recv", 0),
                "rx_rate_kb_s": 0.0,
                "tx_rate_kb_s": 0.0,
            },
        }

    @staticmethod
    def get_service_status(process_name: str) -> Dict[str, Any]:
        found = False
        pid = None
        for proc in psutil.process_iter(["pid", "name"]):
            try:
                if process_name.lower() in proc.info["name"].lower():
                    found = True
                    pid = proc.info["pid"]
                    break
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return {
            "process_name": process_name,
            "running": found,
            "pid": pid,
            "status": "RUNNING" if found else "STOPPED",
        }