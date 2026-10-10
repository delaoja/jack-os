# Operación

## Inicio normal

```powershell
.\.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --host 127.0.0.1 --port 8080
```

Abre `http://127.0.0.1:8080/` y verifica primero el indicador de telemetría.

## Orden recomendado de revisión

1. `GET /health`: confirma que la API está disponible.
2. `GET /telemetry`: verifica fuente, CPU, memoria, disco y red.
3. `GET /proxmox/resources`: confirma el inventario.
4. Revisa el estado y VMID antes de cualquier acción.
5. Usa el chat de IA para diagnóstico, no como autorización automática.
6. Realiza operaciones de energía solo sobre recursos de prueba.

## Telemetría

La fuente esperada es `PROXMOX_VE_CORE`. Si aparece `LOCAL_FALLBACK`, revisa
la conexión o el token de Proxmox. La velocidad de red puede ser `0` en la
primera muestra porque necesita una muestra anterior para calcular la tasa.

## Inventario

El inventario incluye:

- Tipo: `VM` o `LXC`.
- VMID.
- Nombre.
- Nodo.
- Estado.
- CPU y memoria.
- Interfaces de red.
- IPs conocidas.
- Snapshots disponibles.
- Indicadores de configuración GPU cuando existen.

## Acciones de energía

La ruta es:

```text
POST /proxmox/power
```

Payload:

```json
{
  "vmid": 101,
  "action": "shutdown"
}
```

Acciones permitidas: `start`, `shutdown` y `stop`. `shutdown` debe preferirse
para una operación graceful. `stop` puede interrumpir operaciones del sistema
invitado y provocar pérdida de datos no sincronizados.

Antes de probar:

- Confirma que el VMID sea correcto.
- Verifica el estado actual.
- Usa una VM o LXC no crítico.
- Comprueba los permisos del token.
- Mantén un registro del operador y del motivo.

## Diagnóstico de IA

El chat recibe la pregunta, la telemetría y el inventario actual. Una consulta
útil debe ser específica, por ejemplo:

```text
Analiza el consumo actual y señala qué recursos requieren revisión.
```

La respuesta puede contener una recomendación textual y un nivel de riesgo.
Valida siempre la información contra Proxmox antes de actuar.

## Simulación de remediación

`POST /remediate/dry-run` sirve para probar el flujo de análisis sin cambiar
Proxmox:

```json
{
  "target": "node-the-banished",
  "action": "review memory pressure",
  "reason": "memory above operational threshold",
  "operator": "admin",
  "dry_run": true
}
```

La respuesta debe indicar `execution_status=SIMULATED`.

## Apagado

Para detener el servicio de JACK-OS usa `Ctrl+C` en la terminal de Uvicorn.
Para detener una VM o un LXC, usa el procedimiento de cambio controlado de
Proxmox, no una recomendación textual de la IA sin validación.

## Diagnóstico de fallos

| Síntoma | Revisión |
|---|---|
| `LOCAL_FALLBACK` | Host, puerto, token, permisos y certificado Proxmox. |
| Inventario vacío | Nodo disponible y permisos de lectura. |
| Error Gemini | `GOOGLE_API_KEY`, modelo y conectividad externa. |
| Dashboard no carga | Uvicorn, puerto 8080 y directorio `app/ui`. |
| Acción rechazada | VMID, estado, permisos y tipo de recurso. |
