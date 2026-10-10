# JACK-OS

JACK-OS is an observability and operations platform for Proxmox VE
environments. It combines a FastAPI service, a web dashboard, a Proxmox
inventory client, system telemetry, and optional Gemini-assisted diagnostics.
Operators can review node metrics, inspect QEMU virtual machines and LXC
containers, and request operational analysis from a single interface. The AI
provides recommendations; it is not an authorization mechanism and does not
replace operator review. The current branch also exposes power lifecycle
operations, which must remain restricted to trusted administrators. Autonomous
setpoints, persistent rolling averages, resource allowlists, grace periods,
and automatic shutdown policy are not implemented in `FinalBranch`.

## Contents

- [Capabilities](#capabilities)
- [Architecture](#architecture)
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
- [Running JACK-OS](#running-jack-os)
- [Using the dashboard](#using-the-dashboard)
- [API reference](#api-reference)
- [Proxmox client](#proxmox-client)
- [Security](#security)
- [Verification](#verification)
- [Documentation](#documentation)
- [Project structure](#project-structure)
- [Current status and next steps](#current-status-and-next-steps)

## Capabilities

### For operators and non-technical users

- View CPU, memory, disk, and network telemetry in a web dashboard.
- Review the VMs and containers registered in Proxmox.
- Check whether a local process is running.
- Ask the AI copilot to explain current conditions and suggest diagnostics.
- Start or shut down a resource after confirming its VMID and impact.

### For technical users

- FastAPI application with Pydantic request and response models.
- Telemetry from the Proxmox node status API.
- Automatic `psutil` fallback when Proxmox telemetry is unavailable.
- Normalized inventory for QEMU VMs and LXC containers.
- Shared Proxmox client for the API and command-line workflows.
- Optional Gemini integration through `google-genai`.
- Dry-run remediation endpoint for testing diagnostic workflows.
- Static dashboard served by the FastAPI application.

## Architecture

```text
Browser
   |
   v
FastAPI (app/main.py)
   |
   +--> /telemetry ----------> TelemetryCollector
   |                              |
   |                              +--> Proxmox VE
   |                              +--> psutil fallback
   |
   +--> /proxmox/resources --> ProxmoxClient --> Proxmox VE
   |
   +--> /ai/chat ------------> AIDiagnosticEngine --> Gemini
   |
   +--> /remediate/dry-run --> AIDiagnosticEngine
   |
   +--> /proxmox/power ------> ProxmoxClient --> Proxmox VE
```

By default, the application listens on `127.0.0.1:8080` and serves the
dashboard at `/`. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the
component and data-flow description.

## Requirements

- Python 3.10 or later.
- Network access to the Proxmox VE HTTPS API.
- A Proxmox user or API token with the minimum required permissions.
- `GOOGLE_API_KEY` only when Gemini diagnostics are needed.
- Nmap is not required by the application in `FinalBranch`.

## Installation

From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r .\requirements.txt
```

On Linux or macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Create a local configuration file from
[.env.example](.env.example):

```powershell
Copy-Item .env.example .env
notepad .env
```

Do not copy real credentials into the README, documentation, source code, or
commits.

## Configuration

| Variable | Required | Description |
|---|---:|---|
| `HOST` | No | API bind address. Defaults to `127.0.0.1`. |
| `PORT` | No | HTTP port. Defaults to `8080`. |
| `DEBUG` | No | Enables debug mode for `true`, `1`, `yes`, or `on`. |
| `NODE_ID` | No | Identifier used by local fallback telemetry. |
| `PROXMOX_HOST` | For Proxmox | Proxmox host or URL. |
| `PROXMOX_PORT` | No | Proxmox API port. Defaults to `8006`. |
| `PROXMOX_USER` | For Proxmox | Proxmox user or token ID. |
| `PROXMOX_TOKEN` | For Proxmox | Proxmox API token secret. |
| `PROXMOX_NODE` | No | Node used for telemetry. |
| `PROXMOX_VERIFY_SSL` | No | Verifies the HTTPS certificate. Use `true` in production. |
| `GOOGLE_API_KEY` | For AI | Google Gemini API key. |
| `GEMINI_MODEL` | No | Gemini model name. Defaults to `gemini-3.6-flash`. |

For a temporary PowerShell configuration, use:

```powershell
$env:PROXMOX_HOST = "https://pve.example.com"
$env:PROXMOX_USER = "monitor@pam!monitor-token"
$env:PROXMOX_TOKEN = "REPLACE_WITH_TOKEN_SECRET"
```

For persistent configuration, put the values in `.env`. Do not enter
`NAME=value` lines directly as PowerShell commands.

## Running JACK-OS

### Start the API and dashboard

```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 8080
```

You can also run:

```powershell
python .\app\main.py
```

Open the dashboard at:

```text
http://127.0.0.1:8080/
```

FastAPI documentation is available at:

```text
http://127.0.0.1:8080/docs
http://127.0.0.1:8080/redoc
```

### Run the Proxmox inventory client

```powershell
python .\scripts\proxmox_agent.py
```

Review [docs/OPERATIONS.md](docs/OPERATIONS.md) before using power
operations.

## Using the dashboard

1. Start the application with Uvicorn.
2. Open `http://127.0.0.1:8080/`.
3. In **Telemetry**, review CPU, memory, disk, and network values.
4. In **Resources**, refresh the inventory and review each resource's state.
5. In **AI Copilot**, enter a specific diagnostic question.
6. Before using **START** or **STOP**, confirm the VMID and expected impact in
   Proxmox.

The current dashboard exposes power actions for resources. The corresponding
API route does not yet enforce authentication, operator confirmation, or a
resource allowlist. Keep the service bound to localhost or an isolated
management network until those controls are implemented.

## API reference

The API does not currently use an `/api` prefix.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Confirms that JACK-OS is online. |
| `GET` | `/telemetry` | Returns CPU, memory, disk, and network metrics. |
| `GET` | `/process/{process_name}` | Reports whether a process is running. |
| `POST` | `/remediate/dry-run` | Simulates remediation and requests an AI assessment. |
| `GET` | `/proxmox/resources` | Returns the current VM and container inventory. |
| `POST` | `/proxmox/power` | Sends `start`, `shutdown`, or `stop` to a resource. |
| `POST` | `/ai/chat` | Analyzes an operator message with live context. |

Basic PowerShell checks:

```powershell
Invoke-RestMethod http://127.0.0.1:8080/health
Invoke-RestMethod http://127.0.0.1:8080/telemetry
Invoke-RestMethod http://127.0.0.1:8080/proxmox/resources
```

Example power request:

```powershell
$body = @{ vmid = 101; action = "shutdown" } | ConvertTo-Json
Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8080/proxmox/power `
  -ContentType "application/json" `
  -Body $body
```

Run this example only against a non-critical test resource after reviewing
permissions and the target VMID.

## Proxmox client

The client queries nodes, QEMU VMs, and LXC containers. It normalizes resource
data such as:

- Resource type: `VM` or `LXC`.
- VMID, name, node, and current status.
- CPU and memory usage.
- Network configuration and known IP addresses.
- Available snapshots.
- GPU or passthrough configuration hints.

The client distinguishes QEMU and LXC power semantics. Prefer `shutdown` for a
graceful operation. An immediate `stop` can interrupt guest activity and may
cause data loss.

## Security

- Keep `.env` local; it is excluded by `.gitignore`.
- Rotate any credential that has been exposed in a terminal, screenshot,
  conversation, log, or repository.
- Use a dedicated Proxmox account with least privilege.
- Set `PROXMOX_VERIFY_SSL=true` when a trusted certificate is available.
- Keep `HOST=127.0.0.1` until API authentication is implemented.
- Restrict CORS before exposing the service beyond a controlled environment.
- Treat Gemini output as untrusted advice, not as authorization.
- Never execute shell commands generated by the AI.
- Protect `/proxmox/power` with authentication, authorization, confirmation,
  and an explicit resource policy before production use.

`FinalBranch` does not yet implement setpoints, persistent rolling averages,
resource allowlists, protected resources, grace periods, decision auditing, or
fully autonomous shutdown control. These are prerequisites for safe autonomy.
See [docs/SECURITY.md](docs/SECURITY.md) for the current security model.

## Verification

### Validate Python syntax

```powershell
python -m py_compile `
  .\app\config.py `
  .\app\main.py `
  .\app\api\routes.py `
  .\app\core\orchestrator.py `
  .\app\services\ai_diagnostics.py `
  .\app\services\telemetry.py `
  .\scripts\proxmox_agent.py
```

### Check the API

With the service running:

```powershell
Invoke-RestMethod http://127.0.0.1:8080/health
Invoke-RestMethod http://127.0.0.1:8080/telemetry
Invoke-RestMethod http://127.0.0.1:8080/proxmox/resources
```

Expected results:

- `/health` reports `ONLINE`.
- `/telemetry` identifies its source as `PROXMOX_VE_CORE` or
  `LOCAL_FALLBACK`.
- `/proxmox/resources` returns the expected VM and LXC resources.

Test power operations only with a disposable or non-critical resource.

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Installation and configuration](docs/INSTALLATION.md)
- [Operations and API usage](docs/OPERATIONS.md)
- [Security model](docs/SECURITY.md)

## Project structure

```text
.
├── app/
│   ├── api/routes.py               # HTTP contracts and endpoints
│   ├── config.py                  # .env-backed settings
│   ├── core/orchestrator.py       # Orchestration extension point
│   ├── main.py                    # FastAPI application and dashboard
│   ├── services/ai_diagnostics.py # Gemini integration
│   ├── services/telemetry.py      # Proxmox and psutil metrics
│   └── ui/index.html              # Web dashboard
├── scripts/proxmox_agent.py       # Proxmox client and inventory logic
├── requirements.txt
├── .env.example
└── README.md
```

## Current status and next steps

### Available in `FinalBranch`

- Web dashboard.
- FastAPI service.
- Proxmox telemetry with local fallback.
- VM and LXC inventory.
- Gemini diagnostics and contextual chat.
- Dry-run remediation.
- API-based power operations.

### Recommended before production

1. Add API authentication and role-based authorization.
2. Restrict CORS and network exposure.
3. Add an explicit resource allowlist and protected-resource policy.
4. Require human confirmation for `start`, `shutdown`, and `stop`.
5. Implement setpoints, rolling averages, grace periods, and audit logging.
6. Keep AI diagnosis separate from deterministic action authorization.
7. Add automated tests for contracts, errors, permissions, and failure modes.
8. Use trusted TLS certificates and a least-privilege Proxmox account.
