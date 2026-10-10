"""Punto de entrada compatible para el escáner de Proxmox."""

from scripts.proxmox_agent import main


if __name__ == "__main__":
    raise SystemExit(main())
