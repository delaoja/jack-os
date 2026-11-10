import psutil


def get_local_telemetry() -> str:
    try:
        cpu_percent = psutil.cpu_percent(interval=0.1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage("C:\\")
        bytes_per_gb = 1024 ** 3

        return (
            f"CPU usage: {cpu_percent:.1f}%; "
            f"RAM total: {memory.total / bytes_per_gb:.1f} GB, "
            f"available: {memory.available / bytes_per_gb:.1f} GB; "
            f"C: drive usage: {disk.percent:.1f}% "
            f"({disk.used / bytes_per_gb:.1f} / {disk.total / bytes_per_gb:.1f} GB)."
        )
    except Exception as error:
        return f"Local telemetry unavailable: {error}"


def get_proxmox_telemetry() -> str:
    try:
        from app.services.telemetry import TelemetryCollector
        from app.config import settings
        from scripts.proxmox_agent import ProxmoxClient

        status = TelemetryCollector.get_proxmox_status()
        if status is None:
            return "Proxmox HQ (the-banished) telemetry currently unreachable."

        client = ProxmoxClient(
            host=settings.proxmox_host,
            user=settings.proxmox_user,
            token=settings.proxmox_token,
            port=str(settings.proxmox_port),
            verify_ssl=settings.proxmox_verify_ssl,
        )
        nodes = client.nodes()
        inventory = client.inventory()

        node_names = ", ".join(str(node["node"]) for node in nodes)
        vm_count = sum(item.get("type") == "VM" for item in inventory)
        lxc_count = sum(item.get("type") == "LXC" for item in inventory)
        cpu_percent = float(status.get("cpu", 0.0)) * 100
        memory = status.get("memory", {})
        memory_used_gb = memory.get("used", 0) / 1024 ** 3
        memory_total_gb = memory.get("total", 0) / 1024 ** 3
        return (
            f"CPU usage: {cpu_percent:.1f}%; "
            f"RAM used: {memory_used_gb:.1f} / {memory_total_gb:.1f} GB; "
            f"Nodes: {len(nodes)} ({node_names}); "
            f"VMs: {vm_count}; LXCs: {lxc_count}."
        )
    except Exception:
        return "Proxmox HQ (the-banished) telemetry currently unreachable."

import pynvml

def get_gpu_telemetry() -> str:
    try:
        pynvml.nvmlInit()
        handle = pynvml.nvmlDeviceGetHandleByIndex(0) # RTX 4060 es el índice 0
        
        name = pynvml.nvmlDeviceGetName(handle)
        temp = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
        memory = pynvml.nvmlDeviceGetMemoryInfo(handle)
        util = pynvml.nvmlDeviceGetUtilizationRates(handle)
        
        vram_used = round(memory.used / (1024**3), 1)
        vram_total = round(memory.total / (1024**3), 1)
        
        pynvml.nvmlShutdown()
        return f"GPU {name} | Carga: {util.gpu}% | VRAM: {vram_used}GB/{vram_total}GB | Temp: {temp}°C"
    except Exception as e:
        return f"GPU Telemetry Offline: {e}"