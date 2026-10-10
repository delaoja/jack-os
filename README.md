# JACK-OS

Defensive tooling for inventorying and carefully operating QEMU virtual
machines and LXC containers in Proxmox VE, with optional Gemini and Nmap
integration.

> **Scope:** the program performs read-only Proxmox queries by default.
> Create, start, and stop operations require `--interactive --execute` and
> an explicit confirmation for each operation.

## Contents

- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
- [Quick start](#quick-start)
- [Interactive interface](#interactive-interface)
- [Security and limitations](#security-and-limitations)
- [Additional documentation](#additional-documentation)
- [Project structure](#project-structure)
- [Validation](#validation)

## Features

- Inventory of every cluster node visible to the API token.
- QEMU VM and LXC container detection.
- CPU, used/maximum memory, state, network, IPs, and snapshots.
- QEMU Guest Agent IP discovery when available.
- Node, storage, and ISO image discovery.
- Guided VM creation with automatic VMID, ISO, disk, and bridge selection.
- Resource start and type-specific stop operations.
- Optional Gemini report and interactive chat.
- Optional Nmap scans against authorized targets.
- JSON inventory export.

## Requirements

- Python 3.10 or later.
- HTTPS access to Proxmox VE.
- A Proxmox API token with the required permissions.
- Nmap installed only when using `--nmap`.
- `GOOGLE_API_KEY` only when using `--ai` or `--chat`.

## Installation

From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Configuration

Create the local configuration from the example:

```powershell
Copy-Item .env.example .env
```

Fill in `.env`:

```env
PROXMOX_HOST=https://pve.example.com:8006
PROXMOX_USER=monitor@pam
PROXMOX_TOKEN=TOKEN_ID=TOKEN_SECRET
GOOGLE_API_KEY=SET_ONLY_IF_USING_GEMINI
GEMINI_MODEL=gemini-2.0-flash
```

The following `PROXMOX_TOKEN` formats are accepted:

```text
TOKEN_ID=SECRET
user@realm!TOKEN_ID=SECRET
PVEAPIToken=user@realm!TOKEN_ID=SECRET
```

Never commit `.env`, tokens, passwords, or API keys.

## Quick start

Read-only inventory:

```powershell
python proxmox_scanner.py
```

Use a different output file:

```powershell
python proxmox_scanner.py --output inventory.json
```

Gemini report:

```powershell
python proxmox_scanner.py --ai
```

Gemini chat:

```powershell
python proxmox_scanner.py --chat
```

Nmap scan of discovered IPs:

```powershell
python proxmox_scanner.py --nmap
```

Add authorized private targets:

```powershell
python proxmox_scanner.py --nmap `
  --target 192.168.56.20 `
  --target 192.168.56.21
```

Public IPs are rejected by default. Explicitly allow an authorized public
target with:

```powershell
python proxmox_scanner.py --nmap --target 203.0.113.10 --allow-public
```

## Interactive interface

Open the safe mode:

```powershell
python proxmox_scanner.py --interactive
```

Available options:

1. List VMs and containers.
2. View CPU, memory, network, IPs, snapshots, and GPU configuration.
3. Refresh the inventory.
4. Prepare or create a VM.
5. Prepare or stop a VM/LXC.
6. Prepare or start a VM/LXC.
7. Save the inventory.
0. Exit.

To allow real operations:

```powershell
python proxmox_scanner.py --interactive --execute
```

The program requires exact confirmations:

- `CREATE` to create a VM.
- `START` to start a VM or LXC.
- `STOP` to stop a VM or LXC.

Power actions are type-specific:

- QEMU: `qm stop`.
- LXC: `pct shutdown`.

Each action is verified by querying the resulting Proxmox state.

## Security and limitations

- Mutations are disabled unless `--execute` is supplied.
- Nmap targets must be literal IP addresses, not arbitrary hostnames.
- Public IPs require `--allow-public`.
- Optional endpoint failures produce warnings and do not abort the inventory.
- The standard Proxmox API does not provide instantaneous GPU utilization;
  `hostpci`, `mdev`, and `vga` configuration hints are shown when present.
- `qm stop` may cause loss of unsynchronized guest data.
- The code does not delete snapshots, disks, VMs, or containers.

## Additional documentation

- [Installation and configuration](docs/INSTALLATION.md)
- [Operations guide](docs/OPERATIONS.md)
- [Security model](docs/SECURITY.md)
- [Technical architecture](docs/ARCHITECTURE.md)
- [Environment example](.env.example)

## Project structure

```text
.
├── docs/
│   ├── ARCHITECTURE.md
│   ├── INSTALLATION.md
│   ├── OPERATIONS.md
│   └── SECURITY.md
├── scripts/
│   └── proxmox_agent.py
├── .env.example
├── .gitignore
├── proxmox_scanner.py
├── requirements.txt
└── README.md
```

`proxmox_scan.json` is generated output and should be treated as a local
artifact, not source documentation or configuration.

## Validation

```powershell
python -m py_compile .\proxmox_scanner.py .\scripts\proxmox_agent.py
python .\proxmox_scanner.py --help
```
