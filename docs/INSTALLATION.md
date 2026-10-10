# Instalación y configuración

## 1. Preparar Python

```powershell
cd D:\monitor-ia\jack-os
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r .\requirements.txt
```

Si PowerShell bloquea la activación del entorno, puede usarse directamente el
ejecutable:

```powershell
.\.venv\Scripts\python.exe -m pip install -r .\requirements.txt
```

## 2. Crear la configuración

```powershell
Copy-Item .env.example .env
notepad .env
```

Completa los valores de Proxmox. `PROXMOX_TOKEN` debe contener el secreto del
token, nunca el valor real en documentación o commits.

## 3. Cuenta de Proxmox

Se recomienda un usuario dedicado con permisos de lectura para inventario y
telemetría. Los permisos de inicio/apagado solo deben concederse si se usará
`/proxmox/power`, y deben limitarse a los recursos necesarios.

## 4. Gemini

`GOOGLE_API_KEY` es opcional para inventario y telemetría. Es necesaria para
`/ai/chat` y para evaluaciones de IA. Si no está definida, el servicio usa una
respuesta heurística de respaldo y no realiza llamadas externas.

## 5. Iniciar el servicio

```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 8080
```

Visita `http://127.0.0.1:8080/`. Para detener el servicio, usa `Ctrl+C`.

## 6. Primera comprobación

En otra terminal:

```powershell
Invoke-RestMethod http://127.0.0.1:8080/health
Invoke-RestMethod http://127.0.0.1:8080/telemetry
Invoke-RestMethod http://127.0.0.1:8080/proxmox/resources
```

Si falla el acceso a Proxmox, revisa host, puerto, token, permisos y
certificado. Si el endpoint `/telemetry` responde con `LOCAL_FALLBACK`, la
aplicación está funcionando, pero no está usando datos del nodo Proxmox.
