"""
AutoML scoring pipeline — multi-framework support via adapter pattern.

Trains the selected AutoML framework on historical test data, saves metrics,
and provides model retrieval for risk scoring. Defaults to H2O for backward
compatibility when no ``automl_tool`` is specified.
"""
import json
import logging
import os
from typing import Optional

from automl.base import AutoMLResult
from automl.dataset import load_history


# ── Paths (per-framework) ───────────────────────────────────────────────

_BASE_SAVE_DIR = os.path.join(os.path.dirname(__file__), "..", "models", "saved")


def _model_save_dir(automl_tool: str = "h2o") -> str:
    """Return the model save directory for a given framework."""
    return os.path.join(_BASE_SAVE_DIR, automl_tool)


def _model_binary_dir(automl_tool: str = "h2o") -> str:
    """Return the model binary directory for a given framework."""
    return os.path.join(_model_save_dir(automl_tool), "model_binary")


def _metrics_path(automl_tool: str = "h2o") -> str:
    """Return the metrics JSON path for a given framework."""
    return os.path.join(_model_save_dir(automl_tool), "model_metrics.json")


# ── Legacy path constants (backward-compatible) ────────────────────────
MODEL_SAVE_DIR = os.path.join(os.path.dirname(__file__), "..", "models", "saved")
MODEL_BINARY_DIR = os.path.join(MODEL_SAVE_DIR, "h2o_model")


# ── Train ────────────────────────────────────────────────────────────────

def train_and_save_model(
    history_csv_path: str,
    automl_tool: str = "h2o",
    max_runtime_secs: int = 300,
    seed: int = 42,
    dynamic: bool = False,
) -> dict:
    """
    Train the selected AutoML framework on accumulated test history and save.

    Args:
        history_csv_path: Path to the history CSV file.
        automl_tool: Framework name (h2o, autogluon, pycaret, tpot, autosklearn).
        max_runtime_secs: Training time budget.
        seed: Random seed for reproducibility.
        dynamic: If True, compute rolling temporal features (Phase 5/6).

    Returns:
        Model metrics dict (AUC, feature importance, leaderboard, etc.).
    """
    from automl.registry import get_adapter

    history = load_history(path=history_csv_path, dynamic=dynamic)

    if len(history) < 10:
        logging.warning("[AutoML] Not enough history data to train (need >= 10 rows)")
        return {"status": "insufficient_data", "rows": len(history)}

    adapter = get_adapter(automl_tool)

    result: AutoMLResult = adapter.train(
        df=history,
        target="vulnerability_found",
        max_runtime_secs=max_runtime_secs,
        seed=seed,
    )

    # Convert to dict for storage/API response
    model_metrics = result.to_dict()
    model_metrics["status"] = "trained"
    model_metrics["training_rows"] = len(history)
    model_metrics["automl_tool"] = automl_tool

    # Save metrics JSON
    save_dir = _model_save_dir(automl_tool)
    os.makedirs(save_dir, exist_ok=True)
    metrics_file = _metrics_path(automl_tool)
    with open(metrics_file, "w") as f:
        json.dump(model_metrics, f, indent=2, default=str)

    logging.info(
        f"[AutoML:{automl_tool}] Model trained — "
        f"Leader: {model_metrics.get('leader_algo', '?')}, "
        f"AUC: {model_metrics.get('auc', '?')}, "
        f"Training rows: {len(history)}"
    )

    # Persist model binary to disk
    try:
        binary_dir = _model_binary_dir(automl_tool)
        os.makedirs(binary_dir, exist_ok=True)
        adapter.save_model(binary_dir)
    except Exception as e:
        logging.warning(f"[AutoML:{automl_tool}] Could not persist model binary: {e}")

    # Also write to legacy path for backward compat when using H2O
    if automl_tool == "h2o":
        os.makedirs(MODEL_SAVE_DIR, exist_ok=True)
        legacy_metrics = os.path.join(MODEL_SAVE_DIR, "model_metrics.json")
        with open(legacy_metrics, "w") as f:
            json.dump(model_metrics, f, indent=2, default=str)

    return model_metrics


# ── Model retrieval ──────────────────────────────────────────────────────

def get_model(automl_tool: str = "h2o"):
    """Get the currently trained model adapter, or None if not trained.

    For H2O this returns the raw H2O model object (backward compatible).
    For other frameworks this returns the adapter itself (which has .predict()).

    Tries (in order):
    1. Check if the adapter already has a model loaded
    2. For H2O: try server retrieval, then disk reload
    3. For REST adapters: try loading from saved binary
    """
    from automl.registry import get_adapter

    try:
        adapter = get_adapter(automl_tool)
    except ValueError:
        logging.warning(f"[AutoML] Unknown framework: {automl_tool}")
        return None

    # If adapter already has a model, return it
    if adapter.has_model():
        if automl_tool == "h2o":
            return adapter.get_leader()  # backward compat: return raw H2O model
        return adapter

    # Check if we have saved metrics (indicating a model was trained before)
    metrics = get_model_metrics(automl_tool)
    if metrics.get("status") == "untrained":
        return None

    # Try to recover model from disk or server
    if automl_tool == "h2o":
        model_id = metrics.get("leader_model_id")
        if model_id:
            # Try H2O server first
            if adapter.try_fetch_from_server(model_id):
                return adapter.get_leader()

        # Try disk reload
        binary_dir = _model_binary_dir(automl_tool)
        if not os.path.isdir(binary_dir):
            # Try legacy path
            binary_dir = MODEL_BINARY_DIR
        if adapter.load_model(binary_dir):
            return adapter.get_leader()

        logging.warning(f"[AutoML:h2o] Model {model_id} unavailable — retrain required")
        return None
    else:
        # REST-based adapters: try loading from saved binary
        binary_dir = _model_binary_dir(automl_tool)
        if adapter.load_model(binary_dir):
            return adapter

        logging.warning(f"[AutoML:{automl_tool}] No model available — retrain required")
        return None


def get_adapter_for_scoring(automl_tool: str = "h2o"):
    """Get the adapter instance for scoring (always returns adapter, not raw model).

    Unlike get_model(), this always returns the AutoMLAdapter object.
    Used by the refactored scorer which calls adapter.predict() directly.
    """
    from automl.registry import get_adapter

    try:
        adapter = get_adapter(automl_tool)
    except ValueError:
        return None

    if adapter.has_model():
        return adapter

    # Try to recover
    metrics = get_model_metrics(automl_tool)
    if metrics.get("status") == "untrained":
        return None

    if automl_tool == "h2o":
        model_id = metrics.get("leader_model_id")
        if model_id and adapter.try_fetch_from_server(model_id):
            return adapter
        binary_dir = _model_binary_dir(automl_tool)
        if not os.path.isdir(binary_dir):
            binary_dir = MODEL_BINARY_DIR
        if adapter.load_model(binary_dir):
            return adapter
    else:
        binary_dir = _model_binary_dir(automl_tool)
        if adapter.load_model(binary_dir):
            return adapter

    return None


# ── Metrics retrieval ────────────────────────────────────────────────────

def get_model_metrics(automl_tool: str = "h2o") -> dict:
    """Get saved model metrics for the given framework, or status dict if no model."""
    mp = _metrics_path(automl_tool)
    if os.path.exists(mp):
        with open(mp) as f:
            return json.load(f)

    # Fallback: try legacy path for H2O
    if automl_tool == "h2o":
        legacy = os.path.join(MODEL_SAVE_DIR, "model_metrics.json")
        if os.path.exists(legacy):
            with open(legacy) as f:
                return json.load(f)

    return {"status": "untrained"}


def get_all_model_metrics() -> dict[str, dict]:
    """Get saved metrics for ALL frameworks that have been trained.

    Returns dict keyed by framework name, e.g.:
    {"h2o": {...metrics...}, "autogluon": {...metrics...}}
    """
    from automl.registry import list_all

    all_metrics = {}
    for name in list_all():
        m = get_model_metrics(name)
        if m.get("status") != "untrained":
            all_metrics[name] = m
    return all_metrics
