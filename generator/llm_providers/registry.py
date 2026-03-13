"""
LLM Provider Registry — discovers and manages available provider adapters.

Mirrors the automl/registry.py pattern. Provides a single entry point
to obtain a provider by ID, list all registered providers, and check
which ones have API keys configured.
"""
import importlib
import logging

from generator.llm_providers.base import LLMProvider

# ── Registry storage ─────────────────────────────────────────────────────
_PROVIDERS: dict[str, type[LLMProvider]] = {}
_INSTANCES: dict[str, LLMProvider] = {}


def register(provider_cls: type[LLMProvider]) -> type[LLMProvider]:
    """Register a provider class by its PROVIDER_ID.

    Can be used as a decorator on provider class definitions:

        @register
        class ClaudeProvider(LLMProvider):
            PROVIDER_ID = "claude"
            ...
    """
    pid = provider_cls.PROVIDER_ID
    if pid in _PROVIDERS:
        logging.debug(f"[LLMRegistry] Overwriting provider for '{pid}'")
    _PROVIDERS[pid] = provider_cls
    logging.debug(f"[LLMRegistry] Registered provider: {pid}")
    return provider_cls


def get_provider(provider_id: str) -> LLMProvider:
    """Get (or create) a provider instance by ID.

    Raises:
        ValueError: If no provider is registered for the given ID.
    """
    provider_id = provider_id.lower().strip()

    if provider_id in _INSTANCES:
        return _INSTANCES[provider_id]

    if provider_id not in _PROVIDERS:
        available = ", ".join(sorted(_PROVIDERS.keys())) or "(none)"
        raise ValueError(
            f"Unknown LLM provider '{provider_id}'. Available: {available}"
        )

    instance = _PROVIDERS[provider_id]()
    _INSTANCES[provider_id] = instance
    return instance


def list_all() -> list[str]:
    """Return IDs of all registered providers."""
    return sorted(_PROVIDERS.keys())


def list_available() -> list[dict]:
    """Return detailed status for each registered provider.

    Returns list of dicts with id, name, available.
    Used by GET /api/llm/providers endpoint.
    """
    result = []
    for pid in sorted(_PROVIDERS.keys()):
        entry = {
            "id": pid,
            "name": _PROVIDERS[pid].DISPLAY_NAME,
            "available": False,
        }
        try:
            provider = get_provider(pid)
            entry["available"] = provider.is_available()
        except Exception as e:
            logging.debug(f"[LLMRegistry] Error checking {pid}: {e}")
        result.append(entry)
    return result


def clear_instance(provider_id: str) -> None:
    """Remove the cached instance for a provider."""
    provider_id = provider_id.lower().strip()
    _INSTANCES.pop(provider_id, None)


# ── Auto-discover providers on import ────────────────────────────────────
def _auto_discover():
    """Import all provider modules so they self-register via @register."""
    provider_modules = [
        "generator.llm_providers.claude_provider",
        "generator.llm_providers.openai_provider",
        "generator.llm_providers.gemini_provider",
    ]
    for mod_name in provider_modules:
        try:
            importlib.import_module(mod_name)
        except ImportError as e:
            logging.debug(
                f"[LLMRegistry] Provider module not available: {mod_name} ({e})"
            )
        except Exception as e:
            logging.warning(f"[LLMRegistry] Error loading {mod_name}: {e}")


_auto_discover()
