"""Encrypted storage for provider API keys in the agent SQLite database.

Keys are stored encrypted (Fernet, reversible) in the ``provider_api_keys``
table so they can be recovered to authenticate API calls, but never leave
the backend in plain text. The encryption secret is resolved as:

1. ``APP_SECRET_KEY`` environment variable (any passphrase; hashed with
   SHA-256 to derive a valid Fernet key).
2. Auto-generated Fernet key persisted in ``<config_dir>/.secret_key``
   on first use.

If neither is available (e.g. the generated file was deleted), stored
keys can no longer be decrypted and are reported as not configured.

Imported by ``backend/routes/config.py`` and ``backend/agent/agent.py``.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import os
import sqlite3
import sys
from datetime import datetime, timezone
from typing import Any

# ---------------------------------------------------------------------------
# Ensure the project root is in sys.path for absolute imports
# ---------------------------------------------------------------------------
_current_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(os.path.dirname(_current_dir))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from backend.agent.utils.error_logger import log_error
from backend.agent.utils.db import db_transaction, get_connection
from backend.agent.utils.queries import load_query

logger = logging.getLogger(__name__)

PROVIDER_REGISTRY: dict[str, dict[str, str | None]] = {
    # OpenAI-compatible providers (base_url = OpenAI-compatible API root;
    # key validation = ``GET {base_url}/models`` with the key as Bearer).
    # Base URLs taken from models.dev provider pages (``api`` field).
    "groq": {
        "label": "Groq",
        "api_type": "openai-compatible",
        "base_url": "https://api.groq.com/openai/v1",
        "key_url": "https://console.groq.com/keys",
    },
    "openrouter": {
        "label": "OpenRouter",
        "api_type": "openai-compatible",
        "base_url": "https://openrouter.ai/api/v1",
        "key_url": "https://openrouter.ai/settings/keys",
    },
    "openai": {
        "label": "OpenAI",
        "api_type": "openai-compatible",
        "base_url": "https://api.openai.com/v1",
        "key_url": "https://platform.openai.com/api-keys",
    },
    "deepseek": {
        "label": "DeepSeek",
        "api_type": "openai-compatible",
        "base_url": "https://api.deepseek.com/v1",
        "key_url": "https://platform.deepseek.com/api_keys",
    },
    "xai": {
        "label": "xAI",
        "api_type": "openai-compatible",
        "base_url": "https://api.x.ai/v1",
        "key_url": "https://console.x.ai/",
    },
    "togetherai": {
        "label": "Together AI",
        "api_type": "openai-compatible",
        "base_url": "https://api.together.xyz/v1",
        "key_url": "https://api.together.ai/settings/api-keys",
    },
    "fireworks-ai": {
        "label": "Fireworks AI",
        "api_type": "openai-compatible",
        "base_url": "https://api.fireworks.ai/inference/v1",
        "key_url": "https://fireworks.ai/",
    },
    "cerebras": {
        "label": "Cerebras",
        "api_type": "openai-compatible",
        "base_url": "https://api.cerebras.ai/v1",
        "key_url": "https://cloud.cerebras.ai/",
    },
    "mistral": {
        "label": "Mistral AI",
        "api_type": "openai-compatible",
        "base_url": "https://api.mistral.ai/v1",
        "key_url": "https://console.mistral.ai/api-keys",
    },
    "perplexity": {
        "label": "Perplexity",
        "api_type": "openai-compatible",
        "base_url": "https://api.perplexity.ai",
        "key_url": "https://www.perplexity.ai/settings/api",
    },
    "meta": {
        "label": "Meta",
        "api_type": "openai-compatible",
        "base_url": "https://api.meta.ai/v1",
        "key_url": "https://dev.meta.ai/",
    },
    "moonshotai": {
        "label": "Moonshot AI",
        "api_type": "openai-compatible",
        "base_url": "https://api.moonshot.ai/v1",
        "key_url": "https://platform.moonshot.ai/console/api-keys",
    },
    "zhipuai": {
        "label": "Zhipu AI",
        "api_type": "openai-compatible",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "key_url": "https://open.bigmodel.cn/usercenter/apikeys",
    },
    "alibaba": {
        "label": "Alibaba",
        "api_type": "openai-compatible",
        "base_url": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        "key_url": "https://bailian.console.alibabacloud.com/",
    },
    # Google uses its own SDK (no OpenAI-compatible base URL).
    "google": {
        "label": "Google Gemini",
        "api_type": "google",
        "base_url": None,
        "key_url": "https://aistudio.google.com/apikey",
    },
}
"""Curated providers whose API keys can be managed through this module.

``api_type`` is ``"openai-compatible"`` (validated and called through the
OpenAI-compatible ``{base_url}/models`` + chat-completions endpoints) or
``"google"`` (validated and called through the Gemini SDK).
"""


def list_supported() -> list[dict[str, str | None]]:
    """Return the curated provider list for UI dropdowns.

    Returns:
        List of ``{"provider", "label", "api_type", "key_url"}`` dicts
        (``provider`` as in models.dev, no key material).
    """
    try:
        return [
            {
                "provider": pid,
                "label": str(info.get("label") or pid),
                "api_type": str(info.get("api_type") or ""),
                "key_url": info.get("key_url"),
            }
            for pid, info in PROVIDER_REGISTRY.items()
        ]
    except Exception as e:
        log_error(str(e), source="provider_keys.py:list_supported")
        return []


def is_supported(provider: str) -> bool:
    """Check whether a provider id is in the curated registry.

    Args:
        provider: Provider id (as in models.dev, e.g. ``"openrouter"``).

    Returns:
        True if the provider can be managed through this module.
    """
    try:
        return (provider or "").strip().lower() in PROVIDER_REGISTRY
    except Exception as e:
        log_error(str(e), source="provider_keys.py:is_supported")
        return False


_fernet_cache: Any = None
"""Cached ``Fernet`` instance so the secret is resolved once per process."""


def _load_fernet() -> Any:
    """Return a ``Fernet`` instance, resolving the secret lazily.

    Resolution order:

    1. ``APP_SECRET_KEY`` env var → SHA-256 → URL-safe base64 Fernet key.
    2. Generated key persisted at ``<config_dir>/synapseForge/.secret_key``.

    Returns:
        A ``Fernet`` instance, or ``None`` if ``cryptography`` is missing.
    """
    global _fernet_cache
    if _fernet_cache is not None:
        return _fernet_cache
    try:
        from cryptography.fernet import Fernet
    except ImportError as e:
        log_error(str(e), source="provider_keys.py:_load_fernet(import)")
        logger.error("cryptography package is required for provider keys: %s", e)
        return None

    secret = os.getenv("APP_SECRET_KEY", "").strip()
    if secret:
        digest = hashlib.sha256(secret.encode("utf-8")).digest()
        _fernet_cache = Fernet(base64.urlsafe_b64encode(digest))
        return _fernet_cache

    # No APP_SECRET_KEY: use (or create) a locally persisted random key.
    try:
        from backend.agent.utils.config_dir import get_config_dir

        secret_file = get_config_dir() / ".secret_key"
        if secret_file.exists():
            raw = secret_file.read_text(encoding="utf-8").strip()
            if raw:
                _fernet_cache = Fernet(raw.encode("ascii"))
                return _fernet_cache
        key = Fernet.generate_key()
        secret_file.write_text(key.decode("ascii"), encoding="utf-8")
        _fernet_cache = Fernet(key)
        return _fernet_cache
    except Exception as e:
        log_error(str(e), source="provider_keys.py:_load_fernet(secret_file)")
        logger.error("Could not resolve provider-key secret: %s", e)
        return None


def _connect() -> sqlite3.Connection | None:
    """Open a short-lived connection to the agent DB and ensure the schema.

    Returns:
        A new ``sqlite3.Connection``, or ``None`` on failure.
    """
    try:
        conn = get_connection()
        from backend.agent.ddl_setup import setup_database

        setup_database(conn)
        return conn
    except Exception as e:
        log_error(str(e), source="provider_keys.py:_connect")
        logger.error("Could not open agent DB for provider keys: %s", e)
        return None


def save_key(provider: str, api_key: str) -> dict:
    """Encrypt and persist an API key for the given provider.

    Args:
        provider: Curated provider name (as in models.dev, see
        ``PROVIDER_REGISTRY``).
        api_key: The plain-text API key (never stored in clear).

    Returns:
        Contract response ``{"status": "success"|"error", "message": ...}``.
    """
    provider_id = (provider or "").strip().lower()
    if provider_id not in PROVIDER_REGISTRY:
        return {"status": "error", "message": f"Provider inválido: '{provider}'."}
    if not api_key or not api_key.strip():
        return {"status": "error", "message": "La API key no puede estar vacía."}
    fernet = _load_fernet()
    if fernet is None:
        return {
            "status": "error",
            "message": "Cifrado no disponible (falta el paquete 'cryptography').",
        }
    try:
        encrypted = fernet.encrypt(api_key.strip().encode("utf-8")).decode("ascii")
        now = datetime.now().isoformat()
        conn = _connect()
        if conn is None:
            return {"status": "error", "message": "No se pudo abrir la base de datos."}
        try:
            with conn:
                conn.execute(
                    load_query("providers/upsert_key.sql"),
                    (provider_id, encrypted, now),
                )
        finally:
            conn.close()
        # Sync model catalog from models.dev for this provider.
        try:
            from backend.agent.utils.model_catalog import sync_catalog

            sync_catalog(provider_id)
        except Exception as sync_err:
            # Sync failure is non-blocking: the key is already saved.
            log_error(str(sync_err), source="provider_keys.py:save_key:sync_catalog")
            logger.warning("Catalog sync failed for %s: %s", provider_id, sync_err)
        return {"status": "success", "message": f"API key de {provider_id} guardada."}
    except Exception as e:
        log_error(str(e), source="provider_keys.py:save_key")
        return {"status": "error", "message": f"Error guardando la API key: {e}"}


def get_key(provider: str) -> str | None:
    """Return the decrypted API key for a provider, or ``None``.

    Backend-only helper: the decrypted key must never be returned to the
    frontend.

    Args:
        provider: Provider name (as in models.dev).

    Returns:
        The plain-text API key, or ``None`` if not stored / undecryptable.
    """
    provider_id = (provider or "").strip().lower()
    if provider_id not in PROVIDER_REGISTRY:
        return None
    fernet = _load_fernet()
    if fernet is None:
        return None
    try:
        conn = _connect()
        if conn is None:
            return None
        try:
            row = conn.execute(
                load_query("providers/get_encrypted_key.sql"),
                (provider_id,),
            ).fetchone()
        finally:
            conn.close()
        if row is None:
            return None
        key = fernet.decrypt(row["api_key_encrypted"].encode("ascii")).decode("utf-8")
        return key
    except Exception as e:
        log_error(str(e), source="provider_keys.py:get_key")
        return None


def delete_key(provider: str) -> dict:
    """Remove the stored API key for a provider.

    Args:
        provider: Curated provider name (as in models.dev, see
            ``PROVIDER_REGISTRY``).

    Returns:
        Contract response ``{"status": "success"|"error", "message": ...}``.
    """
    provider_id = (provider or "").strip().lower()
    if provider_id not in PROVIDER_REGISTRY:
        return {"status": "error", "message": f"Provider inválido: '{provider}'."}
    try:
        conn = _connect()
        if conn is None:
            return {"status": "error", "message": "No se pudo abrir la base de datos."}
        try:
            with conn:
                cursor = conn.execute(
                    load_query("providers/delete_key.sql"), (provider_id,)
                )
            deleted = cursor.rowcount > 0
            # Also delete the model catalog for this provider.
            if deleted:
                conn.execute(
                    load_query("model_catalog/delete_by_provider.sql"),
                    (provider_id,),
                )
                conn.commit()
        finally:
            conn.close()
        message = (
            f"API key de {provider_id} eliminada."
            if deleted
            else f"No había API key guardada para {provider_id}."
        )
        return {"status": "success", "message": message}
    except Exception as e:
        log_error(str(e), source="provider_keys.py:delete_key")
        return {"status": "error", "message": f"Error eliminando la API key: {e}"}


def list_configured() -> list[dict[str, Any]]:
    """List which providers have an API key configured.

    Never includes the key material itself — only availability status.

    Returns:
        List of ``{"provider": str, "configured": bool}`` dicts, one entry
        per supported provider.
    """
    result: list[dict[str, Any]] = []
    for pid in sorted(PROVIDER_REGISTRY):
        result.append({"provider": pid, "configured": get_key(pid) is not None})
    return result


def resolve_api_key(provider: str) -> str | None:
    """Resolve the effective API key for a provider.

    Keys are resolved **only** from the encrypted DB storage — environment
    variables are never consulted.

    Args:
        provider: Provider name (as in models.dev).

    Returns:
        The API key string, or ``None`` if none is stored.
    """
    return get_key(provider)


def validate_key(provider: str, api_key: str) -> dict:
    """Validate an API key against the provider's live API.

    The key is **not** persisted here — callers should only store it when
    this check succeeds.

    Args:
        provider: Curated provider name (as in models.dev, see
            ``PROVIDER_REGISTRY``).
        api_key: The plain-text API key to verify.

    Returns:
        Contract response ``{"status": "success"|"error", "message": ...}``.
    """
    provider_id = (provider or "").strip().lower()
    if provider_id not in PROVIDER_REGISTRY:
        return {"status": "error", "message": f"Provider inválido: '{provider}'."}
    if not api_key or not api_key.strip():
        return {"status": "error", "message": "La API key no puede estar vacía."}
    key = api_key.strip()
    try:
        if provider_id == "google":
            # Validate by listing models via Google GenAI SDK
            try:
                from google import genai
                client = genai.Client(api_key=key)
                models = list(client.models.list())
                if not models:
                    return {
                        "status": "error",
                        "message": "API key de Google inválida o sin modelos disponibles.",
                    }
            except Exception as e:
                return {
                    "status": "error",
                    "message": f"API key de Google inválida: {e}",
                }
        elif PROVIDER_REGISTRY[provider_id].get("api_type") == "openai-compatible":
            # Validate by listing models via the provider's
            # OpenAI-compatible API (``GET {base_url}/models``).
            import requests

            base_url = str(PROVIDER_REGISTRY[provider_id].get("base_url") or "").rstrip("/")
            label = str(PROVIDER_REGISTRY[provider_id].get("label") or provider_id)
            resp = requests.get(
                f"{base_url}/models",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                timeout=30,
            )
            if resp.status_code == 401:
                return {"status": "error", "message": f"API key de {label} inválida."}
            resp.raise_for_status()
            data = resp.json()
            models = data.get("data", [])
            if not models:
                return {
                    "status": "error",
                    "message": f"API key de {label} inválida o sin modelos disponibles.",
                }
        else:
            return {"status": "error", "message": f"Provider inválido: '{provider}'."}
        return {"status": "success", "message": f"API key de {provider_id} válida."}
    except Exception as e:
        log_error(str(e), source="provider_keys.py:validate_key")
        return {
            "status": "error",
            "message": f"No se pudo validar la API key de {provider_id}: {e}",
        }
