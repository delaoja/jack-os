# JACK-OS Architecture

## Overview

`FinalBranch` combines a FastAPI web application with a reusable Proxmox
client. The browser communicates with HTTP endpoints; it does not connect
directly to Proxmox or Gemini. The API validates request and response models,
collects telemetry, retrieves inventory, and requests AI diagnostics.

## Components

### `app/main.py`

Creates the FastAPI application, registers the lifecycle hooks, enables CORS,
mounts static files, and serves `app/ui/index.html` at `/`.

### `app/config.py`

Loads `.env` through `python-dotenv` and builds the Pydantic `Settings` model.
It centralizes the host, port, node identifier, Proxmox credentials, and
Gemini model settings.

### `app/api/routes.py`

Defines the Pydantic contracts and the health, telemetry, process, dry-run
remediation, inventory, power, and chat endpoints.

### `app/services/telemetry.py`

First queries `/nodes/{node}/status` on Proxmox. If no token is configured or
the query returns no data, it uses `psutil` to provide local metrics. Network
throughput is calculated from two consecutive samples.

### `app/services/ai_diagnostics.py`

Creates the Gemini client when `GOOGLE_API_KEY` is available and sends
operational context for a text assessment. Without a key, it returns a
simulated heuristic response. The AI does not execute an action by itself.

### `scripts/proxmox_agent.py`

Implements `ProxmoxClient`, QEMU VM and LXC container normalization,
configuration and snapshot queries, IP discovery, and power operations. It
also contains the Proxmox command-line interface.

### `app/ui/index.html`

Provides the static dashboard with telemetry, resources, and AI Copilot tabs.
It uses `fetch` to call endpoints on the same application.

## Telemetry flow

```text
GET /telemetry
  -> TelemetryCollector.get_system_metrics()
  -> Proxmox /nodes/{node}/status
  -> CPU/memory/disk/network normalization
  -> Pydantic SystemMetricsResponse
```

When Proxmox is unavailable:

```text
GET /telemetry
  -> psutil.virtual_memory()
  -> psutil.disk_usage("/")
  -> psutil.cpu_percent()
  -> psutil.net_io_counters()
```

## Inventory flow

```text
GET /proxmox/resources
  -> ProxmoxClient.inventory()
  -> /nodes
  -> /nodes/{node}/qemu
  -> /nodes/{node}/lxc
  -> configuration, snapshots, and IPs
  -> normalized resource list
```

The inventory uses `type=VM` for QEMU resources and `type=LXC` for containers.

## AI flow

`POST /ai/chat` receives the operator's question, current telemetry, and
inventory, then sends them to `AIDiagnosticEngine`. The response contains text,
an optional suggested action, and a risk level.

`POST /remediate/dry-run` analyzes a requested action but returns
`execution_status=SIMULATED`; it must not be interpreted as a real operation.

## Power-operation flow

`POST /proxmox/power` receives a VMID and one allowed action: `start`,
`shutdown`, or `stop`. It retrieves the current inventory, locates the
resource, and calls `ProxmoxClient.power_action`. The current route does not
add authentication, an allowlist, or an additional confirmation step. These
controls are required before production exposure.

## Design decisions

- Pydantic validates request and response shapes.
- `requests` calls the Proxmox API.
- `psutil` provides degraded-mode local telemetry.
- Gemini is optional and does not block basic inventory.
- Secrets are loaded from the environment and must not be written in code.
