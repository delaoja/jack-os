# Installation and Configuration

## 1. Prepare Python

```powershell
cd D:\monitor-ia\jack-os
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r .\requirements.txt
```

If PowerShell blocks environment activation, use the environment's Python
executable directly:

```powershell
.\.venv\Scripts\python.exe -m pip install -r .\requirements.txt
```

## 2. Create the configuration

```powershell
Copy-Item .env.example .env
notepad .env
```

Enter the Proxmox settings. `PROXMOX_TOKEN` must contain the token secret.
Never place the actual secret in documentation or commits.

## 3. Proxmox account

Use a dedicated account with read permissions for inventory and telemetry.
Grant start and shutdown permissions only when `/proxmox/power` is required,
and limit those permissions to the necessary resources.

## 4. Gemini

`GOOGLE_API_KEY` is optional for inventory and telemetry. It is required for
`/ai/chat` and AI assessments. If it is not defined, the service uses a
fallback heuristic response and makes no external AI request.

## 5. Start the service

```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 8080
```

Visit `http://127.0.0.1:8080/`. Stop the service with `Ctrl+C`.

## 6. First verification

In a second terminal:

```powershell
Invoke-RestMethod http://127.0.0.1:8080/health
Invoke-RestMethod http://127.0.0.1:8080/telemetry
Invoke-RestMethod http://127.0.0.1:8080/proxmox/resources
```

If Proxmox access fails, check the host, port, token, permissions, and
certificate. If `/telemetry` returns `LOCAL_FALLBACK`, the application is
running but is not using Proxmox node data.
