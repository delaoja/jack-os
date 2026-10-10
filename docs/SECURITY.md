# Security model

## Principles

1. Read-only by default.
2. Human confirmation for mutations.
3. Credentials are loaded only from `.env`.
4. Nmap is restricted to authorized IPs.
5. Errors are explicit; success is never assumed.

## Credentials

Never log or share:

- `PROXMOX_TOKEN`.
- `GOOGLE_API_KEY`.
- Passwords.
- Complete authentication headers.

If a credential is exposed, revoke it and generate a replacement. The
Proxmox account should have only the permissions required for its role.

## Mutating operations

The `--execute` flag is required to create, start, or stop resources. Each
operation also requires an exact confirmation word. The default mode sends no
mutating requests.

## Nmap

The program rejects public IPs by default. Use `--allow-public` only with
explicit, documented authorization.

## Limitations

- The Proxmox API does not always expose instantaneous GPU utilization.
- Without QEMU Guest Agent, not all internal VM IPs can be discovered.
- `qm stop` is not a graceful shutdown.
- A token without sufficient permissions produces HTTP 401 or 403.
