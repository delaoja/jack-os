# Arquitectura de JACK-OS

## Resumen

`FinalBranch` combina una aplicación web FastAPI con un cliente de Proxmox
reutilizable. El navegador consume endpoints HTTP y no habla directamente con
Proxmox ni con Gemini. La API concentra la validación de los contratos,
obtiene telemetría, consulta el inventario y solicita diagnósticos a la IA.

## Componentes

### `app/main.py`

Crea la aplicación FastAPI, registra el ciclo de vida, habilita CORS, monta los
archivos estáticos y sirve `app/ui/index.html` en `/`.

### `app/config.py`

Carga `.env` mediante `python-dotenv` y construye `Settings` con Pydantic.
Centraliza host, puerto, nodo, credenciales de Proxmox y modelo Gemini.

### `app/api/routes.py`

Define los contratos Pydantic y las rutas de salud, telemetría, procesos,
remediación simulada, inventario, energía y chat.

### `app/services/telemetry.py`

Primero consulta `/nodes/{node}/status` de Proxmox. Si no hay token o la
consulta no produce datos, usa `psutil` para devolver métricas locales. La
velocidad de red se calcula a partir de dos muestras consecutivas.

### `app/services/ai_diagnostics.py`

Construye el cliente Gemini cuando existe `GOOGLE_API_KEY` y envía contexto
operativo para obtener una evaluación textual. Sin clave, devuelve una
respuesta heurística simulada. La IA no ejecuta por sí misma una acción.

### `scripts/proxmox_agent.py`

Implementa `ProxmoxClient`, normalización de VMs QEMU y contenedores LXC,
configuración, snapshots, IPs y operaciones de energía. También contiene una
interfaz de consola para el cliente de Proxmox.

### `app/ui/index.html`

Dashboard estático con pestañas de telemetría, recursos y AI Copilot. Usa
`fetch` contra los endpoints de la misma aplicación.

## Flujo de telemetría

```text
GET /telemetry
  -> TelemetryCollector.get_system_metrics()
  -> Proxmox /nodes/{node}/status
  -> normalización CPU/memoria/disco/red
  -> respuesta Pydantic SystemMetricsResponse
```

Cuando Proxmox no está disponible:

```text
GET /telemetry
  -> psutil.virtual_memory()
  -> psutil.disk_usage("/")
  -> psutil.cpu_percent()
  -> psutil.net_io_counters()
```

## Flujo de inventario

```text
GET /proxmox/resources
  -> ProxmoxClient.inventory()
  -> /nodes
  -> /nodes/{node}/qemu
  -> /nodes/{node}/lxc
  -> config, snapshots e IPs
  -> lista normalizada de recursos
```

El inventario distingue `type=VM` para QEMU y `type=LXC` para contenedores.

## Flujo de IA

`POST /ai/chat` obtiene la pregunta del operador, telemetría actual e
inventario, y los envía a `AIDiagnosticEngine`. La respuesta se devuelve como
texto, una acción sugerida opcional y un nivel de riesgo.

`POST /remediate/dry-run` ejecuta el análisis de una acción solicitada, pero
responde con `execution_status=SIMULATED`; no debe interpretarse como una
ejecución real.

## Flujo de energía

`POST /proxmox/power` recibe un VMID y una acción permitida: `start`,
`shutdown` o `stop`. Consulta el inventario actual, localiza el recurso y
llama a `ProxmoxClient.power_action`. La ruta actual no agrega autenticación,
allowlist ni confirmación adicional; estas protecciones son requisitos
pendientes antes de una exposición productiva.

## Decisiones de diseño

- Pydantic valida la forma de entrada y salida.
- `requests` se usa para el API Proxmox.
- `psutil` permite operar en modo degradado para telemetría local.
- Gemini es opcional y no bloquea el inventario básico.
- Los secretos se cargan desde el entorno y no deben escribirse en código.
