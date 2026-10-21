"""
Memory management helpers for Ollama model lifecycle.

Provides functions to unload models from VRAM, check server health,
and restart the server if it crashes.
"""

from __future__ import annotations

import gc
import logging
import subprocess
import time
import os
import sys

_current_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(os.path.dirname(_current_dir))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from backend.agent.utils.error_logger import log_error

logger = logging.getLogger(__name__)


def liberar_modelo(modelo: str, session_id: str | None = None, turn_number: int | None = None, parent_id: str | None = None, source: str = "clean_memory.py:liberar_modelo") -> None:
    """Ask Ollama to unload the model from RAM and run the Python GC.

    Uses two mechanisms:
    1. ``ollama stop`` via CLI
    2. REST API /api/generate with keep_alive=0 (forces the unload)
    Waits 3s for the RAM to be released before continuing.

    Args:
        modelo: Name of the model to unload.
        session_id: Optional session identifier for error logging.
        turn_number: Optional turn number for error logging.
        parent_id: Optional parent session ID for error logging.
        source: Source label for error logging.
    """
    try:
        subprocess.run(
            ["ollama", "stop", modelo],
            capture_output=True, text=True, timeout=30,
        )
    except Exception as e:
        log_error(str(e), session_id=session_id, turn_number=turn_number, parent_id=parent_id, source=source + "(ollama_stop)")
        pass
    try:
        import requests
        requests.post(
            "http://localhost:11434/api/generate",
            json={"model": modelo, "keep_alive": 0},
            timeout=5,
        )
    except Exception as e:
        log_error(str(e), session_id=session_id, turn_number=turn_number, parent_id=parent_id, source=source + "(keep_alive)")
        pass
    time.sleep(1)
    gc.collect()
    gc.collect()

    try:
        import requests
        r = requests.get("http://localhost:11434/api/ps", timeout=5)
        if r.status_code == 200:
            modelos_activos = r.json().get("models", [])
            for m in modelos_activos:
                if m.get("name") == modelo:
                    logger.warning(f"  ⚠ El modelo {modelo} sigue en VRAM pese a keep_alive=0")
                    requests.post(
                        "http://localhost:11434/api/generate",
                        json={"model": modelo, "keep_alive": 0},
                        timeout=5,
                    )
                    time.sleep(1)
                    gc.collect()
    except Exception as e:
        log_error(str(e), session_id=session_id, turn_number=turn_number, parent_id=parent_id, source=source + "(check_ps)")
        pass

    logger.info(f"Memoria liberada para modelo: {modelo}")


def ollama_server_vivo(session_id: str | None = None, turn_number: int | None = None, parent_id: str | None = None) -> bool:
    """Check whether the local Ollama server is running and responding.

    Args:
        session_id: Optional session identifier for error logging.
        turn_number: Optional turn number for error logging.
        parent_id: Optional parent session ID for error logging.

    Returns:
        True if the server responds with HTTP 200, False otherwise.
    """
    try:
        import requests
        r = requests.get("http://localhost:11434/api/tags", timeout=3)
        return r.status_code == 200
    except Exception as e:
        log_error(str(e), session_id=session_id, turn_number=turn_number, parent_id=parent_id, source="clean_memory.py:ollama_server_vivo")
        return False


def liberar_todos_los_modelos(session_id: str | None = None, turn_number: int | None = None, parent_id: str | None = None) -> None:
    """Unload ALL models from VRAM and kill zombie llama-server processes.

    Useful before loading a new model to make sure VRAM is available.

    Steps:
    1. Kill every llama-server.exe process (zombies)
    2. Get the list of loaded models via the API
    3. Unload each model with keep_alive=0
    4. Python GC
    5. Wait 3s for the VRAM to be released

    Args:
        session_id: Optional session identifier for error logging.
        turn_number: Optional turn number for error logging.
        parent_id: Optional parent session ID for error logging.
    """
    # 1. Matar procesos zombie de llama-server
    try:
        subprocess.run(
            ["taskkill", "/F", "/IM", "llama-server.exe"],
            capture_output=True, timeout=10,
        )
        logger.info("Procesos llama-server terminados")
    except Exception as e:
        log_error(str(e), session_id=session_id, turn_number=turn_number, parent_id=parent_id, source="clean_memory.py:liberar_todos(taskkill)")
        logger.debug(f"No se pudieron matar procesos llama-server: {e}")
    
    # 2. Obtener modelos cargados y liberarlos
    try:
        import requests
        r = requests.get("http://localhost:11434/api/ps", timeout=5)
        if r.status_code == 200:
            modelos_activos = r.json().get("models", [])
            if modelos_activos:
                logger.info(f"Liberando {len(modelos_activos)} modelos de VRAM...")
                for m in modelos_activos:
                    nombre = m.get("name", "")
                    if nombre:
                        try:
                            requests.post(
                                "http://localhost:11434/api/generate",
                                json={"model": nombre, "keep_alive": 0},
                                timeout=5,
                            )
                            logger.debug(f"Modelo {nombre} liberado")
                        except Exception as e:
                            log_error(str(e), session_id=session_id, turn_number=turn_number, parent_id=parent_id, source="clean_memory.py:liberar_todos(liberar_modelo)")
                            logger.debug(f"Error liberando {nombre}: {e}")
            else:
                logger.debug("No hay modelos cargados en VRAM")
    except Exception as e:
        log_error(str(e), session_id=session_id, turn_number=turn_number, parent_id=parent_id, source="clean_memory.py:liberar_todos(api_ps)")
        logger.debug(f"Error consultando modelos activos: {e}")
    
    # 3. GC y espera
    time.sleep(1)
    gc.collect()
    gc.collect()
    
    logger.info("VRAM liberada completamente")


def reiniciar_llama_server(session_id: str | None = None, turn_number: int | None = None, parent_id: str | None = None) -> bool:
    """Try to restart llama-server if it is down.

    Args:
        session_id: Optional session identifier for error logging.
        turn_number: Optional turn number for error logging.
        parent_id: Optional parent session ID for error logging.

    Returns:
        True if the server is responding (it already was, or it recovered), False otherwise.
    """
    if ollama_server_vivo(session_id=session_id, turn_number=turn_number, parent_id=parent_id):
        return True

    logger.warning("  llama-server caido. Intentando reiniciar...")

    try:
        subprocess.run(
            ["taskkill", "/F", "/IM", "llama-server.exe"],
            capture_output=True, timeout=10,
        )
    except Exception as e:
        log_error(str(e), session_id=session_id, turn_number=turn_number, parent_id=parent_id, source="clean_memory.py:reiniciar_llama_server(taskkill)")
        pass
    time.sleep(1)

    if ollama_server_vivo(session_id=session_id, turn_number=turn_number, parent_id=parent_id):
        logger.info("  llama-server recuperado.")
        return True

    logger.error("  No se pudo reiniciar llama-server.")
    return False


def obtener_modelo_actual() -> str | None:
    """Get the currently resolved model from the agent singleton.

    Returns:
        The model name, or None if no model is selected.
    """
    try:
        from backend.instances import agent
        return agent._resolved_model
    except Exception:
        return None


if __name__ == '__main__':
    print('clean_memory module — gestión de VRAM para Ollama.')
    print(f'  ollama_server_vivo(): {ollama_server_vivo()}')
    print(f'  modelo actual: {obtener_modelo_actual()}')
    print('  liberar_modelo(model), reiniciar_llama_server() disponibles.')
