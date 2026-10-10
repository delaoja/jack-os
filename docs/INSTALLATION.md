# Installation and configuration

## 1. Prepare Python

Python 3.10 or later and a virtual environment are recommended:

```powershell
cd D:\monitor-ia\jack-os
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## 2. Configure Proxmox

Create a dedicated API token for the scanner. Prefer a service account with
least privilege instead of `root@pam`.

```powershell
Copy-Item .env.example .env
```

Edit `.env`:

```env
PROXMOX_HOST=https://pve.example.com:8006
PROXMOX_USER=monitor@pam
PROXMOX_TOKEN=monitor-token=TOKEN_SECRET
```

The host may be a DNS name or HTTPS URL. Self-signed certificates are
accepted because they are common on internal Proxmox networks.

## 3. Configure optional Gemini support

Only required for `--ai` or `--chat`:

```env
GOOGLE_API_KEY=GEMINI_API_KEY
GEMINI_MODEL=gemini-2.0-flash
```

The model must be available to the configured account and API.

## 4. Configure optional Nmap support

Verify installation:

```powershell
nmap --version
```

The scanner uses `-sV -Pn --top-ports 100 -T3 --open` and must only be used
against owned or explicitly authorized infrastructure.

## 5. Initial verification

```powershell
python .\proxmox_scanner.py --help
python .\proxmox_scanner.py
```

The second command should create `proxmox_scan.json`.
