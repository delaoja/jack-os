# Technical architecture

## Components

### `proxmox_scanner.py`

Console entry point. It re-exports `main` from the primary module so the
project can be run from the repository root:

```powershell
python proxmox_scanner.py
```

### `scripts/proxmox_agent.py`

Contains:

- Proxmox REST client.
- QEMU/LXC inventory normalization.
- JSON persistence.
- Nmap target validation.
- Optional Gemini integration.
- Interactive menu.
- Controlled power and creation operations.

### `requirements.txt`

Runtime dependencies:

- `requests`
- `python-dotenv`
- `google-genai`

## Main flow

```text
.env
  ↓
ProxmoxClient
  ↓
nodes → qemu/lxc → config/snapshots/IPs
  ↓
proxmox_scan.json
  ├── Gemini (--ai/--chat)
  ├── Nmap (--nmap)
  └── interactive interface (--interactive)
```

## Proxmox API endpoints

- `GET /nodes`
- `GET /nodes/{node}/qemu`
- `GET /nodes/{node}/lxc`
- `GET /nodes/{node}/{type}/{vmid}/config`
- `GET /nodes/{node}/{type}/{vmid}/snapshot`
- `GET /nodes/{node}/qemu/{vmid}/agent/network-get-interfaces`
- `GET /nodes/{node}/storage`
- `GET /nodes/{node}/storage/{storage}/content`
- `GET /cluster/nextid`
- Mutating operations only with `--execute`:
  - `POST /nodes/{node}/qemu`
  - `POST /nodes/{node}/{type}/{vmid}/status/start`
  - `POST /nodes/{node}/{type}/{vmid}/status/stop`
  - `POST /nodes/{node}/{type}/{vmid}/status/shutdown`

## Error handling

Required endpoints abort with an explicit error. Optional endpoints, such as
snapshots or Guest Agent, produce warnings and allow the inventory to
continue with partial data.
