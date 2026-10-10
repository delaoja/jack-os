"""Compatible entry point for the Proxmox scanner."""

from scripts.proxmox_agent import main


if __name__ == "__main__":
    raise SystemExit(main())
