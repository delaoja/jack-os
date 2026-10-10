# Operations

## Start the service

```powershell
.\.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --host 127.0.0.1 --port 8080
```

Open `http://127.0.0.1:8080/` and check the telemetry indicator first.

## Recommended review sequence

1. `GET /health`: confirm that the API is available.
2. `GET /telemetry`: verify the source, CPU, memory, disk, and network values.
3. `GET /proxmox/resources`: confirm the current inventory.
4. Review the resource state and VMID before any action.
5. Use the AI chat for diagnosis, not as automatic authorization.
6. Perform power operations only on test resources.

## Telemetry

The expected source is `PROXMOX_VE_CORE`. If the source is
`LOCAL_FALLBACK`, check the Proxmox connection and token. Network rate may be
`0` in the first sample because it requires a previous sample for comparison.

## Inventory

The inventory includes:

- Type: `VM` or `LXC`.
- VMID.
- Name.
- Node.
- Status.
- CPU and memory usage.
- Network interfaces.
- Known IP addresses.
- Available snapshots.
- GPU configuration indicators when present.

## Power operations

The endpoint is:

```text
POST /proxmox/power
```

Payload:

```json
{
  "vmid": 101,
  "action": "shutdown"
}
```

Allowed actions are `start`, `shutdown`, and `stop`. Prefer `shutdown` for a
graceful operation. `stop` can interrupt guest activity and cause unsynchronized
data loss.

Before testing:

- Confirm the VMID.
- Check the current state.
- Use a non-critical VM or LXC container.
- Verify the token permissions.
- Record the operator and the reason for the change.

## AI diagnostics

The chat receives the operator's question, current telemetry, and inventory. A
useful question should be specific, for example:

```text
Analyze the current resource usage and identify resources that require review.
```

The response may contain a recommendation and a risk level. Always validate
the information against Proxmox before taking action.

## Remediation simulation

`POST /remediate/dry-run` tests the analysis workflow without changing Proxmox:

```json
{
  "target": "node-the-banished",
  "action": "review memory pressure",
  "reason": "memory above operational threshold",
  "operator": "admin",
  "dry_run": true
}
```

The response should report `execution_status=SIMULATED`.

## Shutdown

Stop JACK-OS with `Ctrl+C` in the Uvicorn terminal. To stop a VM or LXC
container, use a controlled Proxmox change procedure rather than acting on an
unvalidated AI recommendation.

## Troubleshooting

| Symptom | Check |
|---|---|
| `LOCAL_FALLBACK` | Proxmox host, port, token, permissions, and certificate. |
| Empty inventory | Node availability and read permissions. |
| Gemini error | `GOOGLE_API_KEY`, model name, and external connectivity. |
| Dashboard does not load | Uvicorn, port `8080`, and `app/ui`. |
| Action rejected | VMID, resource state, permissions, and resource type. |
