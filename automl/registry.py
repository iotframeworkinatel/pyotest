"""
AutoML Framework Registry — discovers and manages available framework adapters.

Provides a single entry point for the rest of the pipeline to obtain the
correct adapter by name, list all registered frameworks, and check which
ones are currently reachable.
"""
import logging
from typing import Optional

from automl.base import AutoMLAdapter

# ── Registry storage ─────────────────────────────────────────────────────
_ADAPTERS: dict[str, type[AutoMLAdapter]] = {}
_INSTANCES: dict[str, AutoMLAdapter] = {}


def register(adapter_cls: type[AutoMLAdapter]) -> type[AutoMLAdapter]:
    """Register an adapter class by its FRAMEWORK_NAME.

    Can be used as a decorator on adapter class definitions:

        @register
        class H2OAdapter(AutoMLAdapter):
            FRAMEWORK_NAME = "h2o"
            ...
    """
    name = adapter_cls.FRAMEWORK_NAME
    if name in _ADAPTERS:
        logging.debug(f"[Registry] Overwriting adapter for '{name}'")
    _ADAPTERS[name] = adapter_cls
    logging.debug(f"[Registry] Registered adapter: {name}")
    return adapter_cls


def get_adapter(name: str) -> AutoMLAdapter:
    """Get (or create) an adapter instance by framework name.

    Raises:
        ValueError: If no adapter is registered for the given name.
    """
    name = name.lower().strip()

    if name in _INSTANCES:
        return _INSTANCES[name]

    if name not in _ADAPTERS:
        available = ", ".join(sorted(_ADAPTERS.keys())) or "(none)"
        raise ValueError(
            f"Unknown AutoML framework '{name}'. "
            f"Available: {available}"
        )

    adapter = _ADAPTERS[name]()
    _INSTANCES[name] = adapter
    return adapter


def list_all() -> list[str]:
    """Return names of all registered frameworks (whether reachable or not)."""
    return sorted(_ADAPTERS.keys())


def list_available() -> list[str]:
    """Return names of registered frameworks that are currently reachable."""
    available = []
    for name in sorted(_ADAPTERS.keys()):
        try:
            adapter = get_adapter(name)
            if adapter.is_available():
                available.append(name)
        except Exception as e:
            logging.debug(f"[Registry] {name} not available: {e}")
    return available


def get_framework_status() -> list[dict]:
    """Return detailed status for each registered framework.

    Returns a list of dicts with ``name``, ``available``, and ``has_model``.
    Used by the ``GET /api/automl/frameworks`` endpoint.
    """
    statuses = []
    for name in sorted(_ADAPTERS.keys()):
        entry = {"name": name, "available": False, "has_model": False}
        try:
            adapter = get_adapter(name)
            entry["available"] = adapter.is_available()
            entry["has_model"] = adapter.has_model()
        except Exception as e:
            logging.debug(f"[Registry] Error checking {name}: {e}")
        statuses.append(entry)
    return statuses


def clear_instance(name: str) -> None:
    """Remove the cached instance for a framework (e.g. after model reset)."""
    name = name.lower().strip()
    _INSTANCES.pop(name, None)


# ── Auto-discover adapters on import ─────────────────────────────────────
def _auto_discover():
    """Import all adapter modules so they self-register via @register."""
    import importlib
    adapter_modules = [
        "automl.adapters.h2o_adapter",
        "automl.adapters.autogluon_adapter",
        "automl.adapters.pycaret_adapter",
        "automl.adapters.tpot_adapter",
        "automl.adapters.autosklearn_adapter",
    ]
    for mod_name in adapter_modules:
        try:
            importlib.import_module(mod_name)
        except ImportError as e:
            logging.debug(f"[Registry] Adapter module not available: {mod_name} ({e})")
        except Exception as e:
            logging.warning(f"[Registry] Error loading {mod_name}: {e}")


_auto_discover()
