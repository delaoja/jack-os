# jack-os
AI-director for sysadmin-copilot

## Escáner defensivo de Proxmox

Instala las dependencias:

```powershell
python -m pip install -r requirements.txt
```

Copia `.env.example` como `.env` y completa `PROXMOX_HOST`,
`PROXMOX_USER` y `PROXMOX_TOKEN`. `GOOGLE_API_KEY` solo es necesaria para
`--ai` o `--chat`.

Comandos disponibles:

```powershell
python proxmox_scanner.py
python proxmox_scanner.py --nmap
python proxmox_scanner.py --nmap --target 192.168.56.20
python proxmox_scanner.py --ai
python proxmox_scanner.py --chat
```

El inventario se guarda por defecto en `proxmox_scan.json`. Nmap solo se
ejecuta con `--nmap`, acepta múltiples `--target` y rechaza IPs públicas por
defecto; usa `--allow-public` únicamente con autorización explícita.

El escáner es de solo lectura: no apaga, elimina, modifica ni reinicia VMs o
contenedores.
