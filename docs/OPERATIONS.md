# Operations guide

## Inventory

```powershell
python proxmox_scanner.py
```

The inventory includes QEMU VMs and LXC containers and is saved to
`proxmox_scan.json`.

## Safe menu

```powershell
python proxmox_scanner.py --interactive
```

This mode allows queries, refreshes, and operation previews without modifying
Proxmox.

## Real operations

Only after reviewing the inventory and permissions:

```powershell
python proxmox_scanner.py --interactive --execute
```

### Create a VM

Option 4 requests:

- Available node.
- Name.
- Explicit VMID or a free VMID obtained from Proxmox.
- CPU and memory.
- Disk storage.
- Existing ISO.
- Disk size.
- Operating system type.
- Network bridge.

Confirm by typing exactly:

```text
CREATE
```

### Start a resource

Option 6 uses `qm start` for QEMU or `pct start` for LXC and waits for
`running`. Confirm with:

```text
START
```

### Stop a resource

Option 5 uses `qm stop` for QEMU and `pct shutdown` for LXC and waits for
`stopped`. Confirm with:

```text
STOP
```

`qm stop` is immediate and may cause loss of unsynchronized guest data.

## Gemini

```powershell
python proxmox_scanner.py --ai
python proxmox_scanner.py --chat
```

Gemini only analyzes the received inventory; it does not execute commands.

## Nmap

```powershell
python proxmox_scanner.py --nmap
python proxmox_scanner.py --nmap --target 192.168.56.20
```

Manual targets may be repeated. Public IPs require `--allow-public`.

## Expected warnings

`QEMU Guest Agent unavailable` means the guest IP could not be obtained from
inside that VM. The rest of the inventory can continue. For better
visibility, install and enable `qemu-guest-agent` inside the VM and enable
the agent in its Proxmox configuration.
