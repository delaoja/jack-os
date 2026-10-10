# Modelo de seguridad

## Principios

1. Mantener el servicio en `127.0.0.1` mientras no exista autenticación.
2. Usar un usuario Proxmox dedicado y de mínimo privilegio.
3. Mantener los secretos únicamente en `.env` o en un gestor de secretos.
4. Tratar las respuestas de Gemini como recomendaciones no confiables.
5. Probar acciones destructivas únicamente sobre recursos no críticos.
6. Registrar quién solicita una operación y por qué.

## Credenciales

No publiques ni registres:

- `PROXMOX_TOKEN`.
- `GOOGLE_API_KEY`.
- Cabeceras `Authorization`.
- Contraseñas o archivos `.env`.

Si una credencial aparece en una conversación, captura, log o repositorio,
revócala y genera una nueva. El archivo `.gitignore` excluye `.env`, pero esa
exclusión no sustituye la rotación de una credencial ya expuesta.

## Superficie de ataque actual

La API de esta rama no implementa autenticación. Además, CORS permite todos
los orígenes y el endpoint `/proxmox/power` acepta acciones de energía sin una
allowlist de recursos. Por tanto:

- No publiques el puerto 8080 en Internet.
- No lo expongas directamente en una red no confiable.
- No habilites `--host 0.0.0.0` sin agregar autenticación, TLS y firewall.
- Restringe CORS a los orígenes reales del dashboard.
- Agrega autorización por rol antes de habilitar operación remota.

## Proxmox

La cuenta de monitoreo debería poder leer únicamente el clúster necesario.
Los permisos de energía deben separarse o limitarse por recurso. Activa
`PROXMOX_VERIFY_SSL=true` cuando el certificado sea confiable; no desactives la
verificación como solución permanente a un certificado mal configurado.

## IA

La IA recibe datos de telemetría, inventario y la consulta del operador.
Evita incluir secretos, tokens o información innecesaria en el contexto.
Nunca ejecutes comandos construidos a partir de texto generado por Gemini.
Una recomendación debe pasar por reglas deterministas, autorización y
confirmación humana.

## Capacidades que faltan antes de autonomía

La rama `FinalBranch` todavía no implementa:

- Setpoints configurables.
- Promedios móviles e histórico persistente.
- Lista de recursos permitidos.
- Lista de recursos protegidos.
- Periodo de gracia frente a una alerta.
- Auditoría estructurada de decisiones.
- Confirmación humana para acciones de energía.
- Autenticación de operador.

Estas capacidades deben implementarse antes de permitir apagados automáticos.
