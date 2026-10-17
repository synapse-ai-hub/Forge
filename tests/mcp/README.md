<p align="center">
  <img src="https://github.com/synapse-ai-hub/sources/raw/main/logo_transparente.png" alt="Logo" width="150">
</p>

---

<h1 align="center">Tests MCP — synapseForge</h1>

---

Tests de la integración MCP contra servidores MCP reales. `echo_server.py` es un servidor mínimo (una tool, `echo`) que se levanta por stdio, streamable HTTP y SSE, y los tests usan las funciones reales de `mcp_helper`, `config_dir` y las rutas de `agent_items` y `listings`. Cada test usa un directorio de configuración temporal, así que `mcp.json` del usuario nunca se lee ni se escribe.

---

## Requisitos

- Python 3.12+
- `pytest`
- No requiere backend ni API keys. Los servidores de prueba se levantan como subprocesos en puertos libres.

---

## Uso

```bash
pytest tests/mcp
pytest tests/mcp -v
```

---

## Tests disponibles

| Archivo | Test | Qué verifica |
|---------|------|--------------|
| `test_mcp_transports.py` | `test_stdio_server_discovery_and_call` | Descubrimiento y llamada de una tool por stdio |
| | `test_streamable_http_server_discovery_and_call` | Lo mismo por streamable HTTP |
| | `test_sse_server_discovery_and_call` | Lo mismo por SSE |
| | `test_transport_is_inferred_when_not_declared` | Sin `transport`, un `command` es stdio y una URL es http |
| | `test_health_is_a_real_handshake_for_every_transport` | El health hace un handshake MCP real: un endpoint que no habla MCP figura como `failed` |
| | `test_disabled_server_is_not_discovered_nor_executed_nor_counted` | Un servidor con `disabled` no se descubre, no se ejecuta, no cuenta como configurado y su health es `disabled` |
| | `test_enabled_false_written_by_hand_is_honored_and_normalized` | `enabled: false` se respeta y el interruptor lo normaliza a `disabled` |
| | `test_toggle_of_unknown_server_returns_none` | Activar un servidor inexistente devuelve `None` |
| | `test_broken_mcp_json_is_reported_not_silently_empty` | Un `mcp.json` inválido se informa en vez de verse como «sin servidores» |
| | `test_save_is_atomic_and_leaves_no_temp_file` | El guardado de `mcp.json` no deja archivos temporales |
| `test_mcp_routes.py` | `test_toggle_endpoint_writes_the_json_and_updates_the_registry` | `PUT /api/agent/mcp/{label}/enabled` escribe el JSON y reconstruye el registry real |
| | `test_toggle_endpoint_validates_input` | El endpoint valida `enabled` y el servidor |
| | `test_listing_reports_a_broken_mcp_json` | `GET /api/config/mcp` informa el JSON inválido en `error` |
