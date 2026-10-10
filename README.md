# JACK-OS

JACK-OS es una plataforma de observabilidad y operación para entornos
Proxmox VE. Su objetivo es reunir en una sola interfaz la telemetría del
servidor, el inventario de máquinas virtuales y contenedores, y el apoyo de
una IA para diagnóstico operativo. El proyecto incluye una API FastAPI, un
dashboard web y un cliente Python para consultar Proxmox. La IA analiza
telemetría e inventario y devuelve recomendaciones; no debe considerarse un
sustituto de la revisión del operador. Las acciones de energía disponibles en
la API pueden iniciar o apagar recursos y, por eso, deben protegerse antes de
exponer el servicio fuera de una red de administración. Esta rama incluye
telemetría en tiempo real, inventario QEMU/LXC, chat operativo y simulación de
remediación. El monitoreo autónomo basado en setpoints, promedios históricos,
allowlist y periodo de gracia todavía no está implementado en `FinalBranch`.

## Índice

- [Qué incluye](#qué-incluye)
- [Arquitectura en una vista](#arquitectura-en-una-vista)
- [Requisitos](#requisitos)
- [Instalación](#instalación)
- [Configuración](#configuración)
- [Ejecución](#ejecución)
- [Uso del dashboard](#uso-del-dashboard)
- [API disponible](#api-disponible)
- [Cliente de Proxmox](#cliente-de-proxmox)
- [Seguridad y límites](#seguridad-y-límites)
- [Verificación](#verificación)
- [Documentación adicional](#documentación-adicional)
- [Estructura del proyecto](#estructura-del-proyecto)
- [Estado actual y próximos pasos](#estado-actual-y-próximos-pasos)

## Qué incluye

### Para personal no técnico

- Una pantalla web para observar CPU, memoria, disco y red.
- Visualización de las VMs y contenedores registrados en Proxmox.
- Consulta del estado de procesos del sistema.
- Un espacio de conversación con la IA para pedir explicaciones y
  recomendaciones.
- Acciones de inicio y apagado visibles desde la pantalla de recursos.

### Para personal técnico

- API HTTP basada en FastAPI y contratos Pydantic.
- Telemetría obtenida del estado del nodo Proxmox.
- Fallback automático a `psutil` si Proxmox no responde o no hay token.
- Inventario normalizado de QEMU y LXC.
- Cliente Proxmox reutilizado por API y herramienta de consola.
- Integración opcional con Gemini mediante `google-genai`.
- Endpoint de remediación en modo simulación.
- Dashboard estático servido por la propia aplicación.

## Arquitectura en una vista

```text
Navegador
    |
    v
FastAPI (app/main.py)
    |
    +--> /telemetry ----------> TelemetryCollector
    |                              |
    |                              +--> Proxmox VE
    |                              +--> psutil (fallback local)
    |
    +--> /proxmox/resources --> ProxmoxClient --> Proxmox VE
    |
    +--> /ai/chat ------------> AIDiagnosticEngine --> Gemini
    |
    +--> /remediate/dry-run --> AIDiagnosticEngine
    |
    +--> /proxmox/power ------> ProxmoxClient --> Proxmox VE
```

La aplicación se inicia en `127.0.0.1:8080` por defecto y sirve el dashboard
en `/`. La documentación de cada componente está en
[docs/ARCHITECTURE.md](D:/monitor-ia/jack-os/docs/ARCHITECTURE.md).

## Requisitos

- Windows, Linux o macOS.
- Python 3.10 o posterior.
- Acceso de red al API HTTPS de Proxmox VE.
- Un usuario o token de Proxmox con permisos mínimos de lectura.
- `GOOGLE_API_KEY` solamente si se desea usar el diagnóstico de Gemini.
- Nmap no es requerido por la aplicación de `FinalBranch`.

## Instalación

Desde la raíz del proyecto:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r .\requirements.txt
```

En Linux/macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Usa [.env.example](D:/monitor-ia/jack-os/.env.example) como plantilla y crea
el archivo local `.env`. Nunca copies secretos reales al README, a la
documentación ni al repositorio.

## Configuración

Variables principales:

| Variable | Obligatoria | Descripción |
|---|---:|---|
| `HOST` | No | Dirección de escucha de la API. Por defecto `127.0.0.1`. |
| `PORT` | No | Puerto HTTP. Por defecto `8080`. |
| `DEBUG` | No | Activa el modo debug si es `true`, `1`, `yes` u `on`. |
| `NODE_ID` | No | Identificador usado por la telemetría local. |
| `PROXMOX_HOST` | Sí para Proxmox | Host o dirección del servidor Proxmox. |
| `PROXMOX_PORT` | No | Puerto de Proxmox. Por defecto `8006`. |
| `PROXMOX_USER` | Sí para Proxmox | Usuario/token ID de Proxmox. |
| `PROXMOX_TOKEN` | Sí para Proxmox | Secreto del token. |
| `PROXMOX_NODE` | No | Nodo consultado por la telemetría. |
| `PROXMOX_VERIFY_SSL` | No | Verifica el certificado HTTPS. Se recomienda `true` en producción. |
| `GOOGLE_API_KEY` | Solo IA | Clave de Google Gemini. |
| `GEMINI_MODEL` | No | Modelo Gemini; por defecto `gemini-3.6-flash`. |

En PowerShell, las variables temporales se escriben así:

```powershell
$env:PROXMOX_HOST = "https://pve.example.com"
$env:PROXMOX_USER = "monitor@pam!monitor-token"
$env:PROXMOX_TOKEN = "TOKEN_SECRET"
```

Para configuración persistente, escribe las variables en `.env`; no las
ejecutes como comandos de PowerShell.

## Ejecución

### Dashboard y API

```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 8080
```

También es posible ejecutar:

```powershell
python .\app\main.py
```

Abre en el navegador:

```text
http://127.0.0.1:8080/
```

Documentación interactiva de FastAPI:

```text
http://127.0.0.1:8080/docs
http://127.0.0.1:8080/redoc
```

### Cliente de inventario

```powershell
python .\scripts\proxmox_agent.py
```

El cliente de consola está orientado a inventario y operaciones de Proxmox.
Consulta [docs/OPERATIONS.md](D:/monitor-ia/jack-os/docs/OPERATIONS.md) antes
de usar acciones de energía.

## Uso del dashboard

1. Inicia la aplicación con Uvicorn.
2. Abre `http://127.0.0.1:8080/`.
3. En **Telemetry**, revisa CPU, memoria, disco y red.
4. En **Resources**, actualiza el inventario y revisa el estado de cada VM o
   LXC.
5. En **AI Copilot**, escribe una consulta operacional usando lenguaje
   natural.
6. Antes de usar `START` o `STOP`, confirma el VMID y la operación en Proxmox.

La interfaz actual muestra acciones de energía para recursos. El endpoint
correspondiente no implementa todavía una política de allowlist, confirmación
humana, autenticación de operador ni un modo autónomo seguro; por eso debe
mantenerse restringido a localhost o a una red de administración confiable.

## API disponible

La API no usa actualmente un prefijo `/api`.

| Método | Ruta | Propósito |
|---|---|---|
| `GET` | `/health` | Comprueba que JACK-OS está en línea. |
| `GET` | `/telemetry` | Obtiene CPU, memoria, disco y red. |
| `GET` | `/process/{process_name}` | Revisa si un proceso está activo. |
| `POST` | `/remediate/dry-run` | Simula una remediación y obtiene evaluación de IA. |
| `GET` | `/proxmox/resources` | Consulta VMs y contenedores en Proxmox. |
| `POST` | `/proxmox/power` | Envía `start`, `shutdown` o `stop` a un recurso. |
| `POST` | `/ai/chat` | Analiza una consulta con telemetría e inventario actual. |

Ejemplos:

```powershell
Invoke-RestMethod http://127.0.0.1:8080/health
Invoke-RestMethod http://127.0.0.1:8080/telemetry
Invoke-RestMethod http://127.0.0.1:8080/proxmox/resources
```

Para una acción de energía:

```powershell
$body = @{ vmid = 101; action = "shutdown" } | ConvertTo-Json
Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8080/proxmox/power `
  -ContentType "application/json" `
  -Body $body
```

Usa este ejemplo solamente con un recurso de prueba y con permisos revisados.

## Seguridad y límites

- `.env` está excluido por `.gitignore`; no debe compartirse.
- Las credenciales expuestas deben revocarse y reemplazarse.
- Usa una cuenta de Proxmox dedicada con mínimo privilegio.
- Activa `PROXMOX_VERIFY_SSL=true` cuando exista una CA confiable.
- Mantén `HOST=127.0.0.1` mientras no exista autenticación para la API.
- `allow_origins=["*"]` está configurado actualmente para desarrollo; debe
  restringirse antes de publicar el dashboard.
- Los endpoints `/proxmox/power` y `/ai/chat` no tienen autenticación propia.
- Un diagnóstico de Gemini es una recomendación, no una autorización.
- La aplicación no debe ejecutar comandos recibidos directamente de la IA.
- La rama actual no incluye todavía setpoints, promedios móviles persistentes,
  allowlist de apagado, recursos protegidos, periodo de gracia ni bitácora de
  decisiones autónomas.

Consulta [docs/SECURITY.md](D:/monitor-ia/jack-os/docs/SECURITY.md) para el
modelo de amenazas y las medidas de operación segura.

## Verificación

### Sintaxis y ayuda

```powershell
python -m py_compile .\app\config.py .\app\main.py .\app\api\routes.py .\app\core\orchestrator.py .\app\services\ai_diagnostics.py .\app\services\telemetry.py .\scripts\proxmox_agent.py
python -m uvicorn app.main:app --help
```

### Comprobación funcional

Con la aplicación ejecutándose:

```powershell
Invoke-RestMethod http://127.0.0.1:8080/health
Invoke-RestMethod http://127.0.0.1:8080/telemetry
Invoke-RestMethod http://127.0.0.1:8080/proxmox/resources
```

Revisa que `/health` devuelva `ONLINE`, que `/telemetry` indique su fuente y
que el inventario contenga los recursos esperados. Las pruebas de energía
deben realizarse únicamente sobre una VM o contenedor no crítico.

## Documentación adicional

- [Arquitectura](D:/monitor-ia/jack-os/docs/ARCHITECTURE.md)
- [Instalación y configuración](D:/monitor-ia/jack-os/docs/INSTALLATION.md)
- [Operación y API](D:/monitor-ia/jack-os/docs/OPERATIONS.md)
- [Seguridad](D:/monitor-ia/jack-os/docs/SECURITY.md)

## Estructura del proyecto

```text
.
├── app/
│   ├── api/routes.py              # Contratos y endpoints HTTP
│   ├── config.py                 # Configuración desde .env
│   ├── core/orchestrator.py      # Punto reservado para orquestación
│   ├── main.py                   # Aplicación FastAPI y dashboard
│   ├── services/ai_diagnostics.py# Integración Gemini
│   ├── services/telemetry.py     # Métricas Proxmox/psutil
│   └── ui/index.html             # Dashboard web
├── scripts/proxmox_agent.py      # Cliente e inventario Proxmox
├── requirements.txt
├── .env.example
└── README.md
```

## Estado actual y próximos pasos

### Disponible en `FinalBranch`

- Dashboard web operativo.
- API FastAPI.
- Inventario de VMs y LXC.
- Telemetría Proxmox con fallback local.
- Diagnóstico Gemini y chat contextual.
- Simulación de remediación.
- Acciones de energía mediante API.

### Recomendado antes de producción

1. Añadir autenticación y autorización a la API.
2. Restringir CORS y el host de escucha.
3. Implementar allowlist y recursos protegidos para acciones de energía.
4. Añadir confirmación humana para `start`, `shutdown` y `stop`.
5. Implementar setpoints, promedios móviles, periodo de gracia y auditoría.
6. Separar diagnóstico de IA de la ejecución de acciones.
7. Añadir pruebas automatizadas para contratos, errores y permisos.
8. Usar certificados TLS y un usuario Proxmox de mínimo privilegio.
