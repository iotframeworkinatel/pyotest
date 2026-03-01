"""
AutoML scoring pipeline — simplified for test case generation.
Trains H2O model on historical test data and provides risk scoring.
"""
import glob
import json
import logging
import os

from automl.dataset import load_history
from automl.train import train_automl, extract_model_metrics


MODEL_SAVE_DIR = os.path.join(os.path.dirname(__file__), "..", "models", "saved")
MODEL_BINARY_DIR = os.path.join(MODEL_SAVE_DIR, "h2o_model")


def train_and_save_model(history_csv_path: str) -> dict:
    """
    Train H2O AutoML on accumulated test history and save the model.
    Returns model metrics (AUC, feature importance, etc.).
    """
    history = load_history(path=history_csv_path)

    if len(history) < 10:
        logging.warning("[AutoML] Not enough history data to train (need >= 10 rows)")
        return {"status": "insufficient_data", "rows": len(history)}

    aml = train_automl(history)

    model_metrics = extract_model_metrics(aml)
    model_metrics["status"] = "trained"
    model_metrics["training_rows"] = len(history)

    # Save model reference for later scoring
    os.makedirs(MODEL_SAVE_DIR, exist_ok=True)
    metrics_path = os.path.join(MODEL_SAVE_DIR, "model_metrics.json")
    with open(metrics_path, "w") as f:
        json.dump(model_metrics, f, indent=2, default=str)

    logging.info(
        f"[AutoML] Model trained — Leader: {model_metrics.get('leader_algo', '?')}, "
        f"AUC: {model_metrics.get('auc', '?')}, "
        f"Training rows: {len(history)}"
    )

    # Store model object for scoring (in-memory reference)
    _model_cache["leader"] = aml.leader
    _model_cache["aml"] = aml

    # Persist model binary to disk so it survives container/H2O restarts
    try:
        import h2o
        os.makedirs(MODEL_BINARY_DIR, exist_ok=True)
        # Remove previous saved model files
        for old in glob.glob(os.path.join(MODEL_BINARY_DIR, "*")):
            try:
                os.remove(old)
            except OSError:
                pass
        saved_path = h2o.download_model(aml.leader, path=MODEL_BINARY_DIR)
        logging.info(f"[AutoML] Model binary saved to: {saved_path}")
    except Exception as e:
        logging.warning(f"[AutoML] Could not persist model binary to disk: {e}")

    return model_metrics


def get_model():
    """Get the currently trained model, or None if not trained.

    Tries (in order):
    1. In-memory cache (fastest)
    2. Retrieve by model ID from H2O server (if server kept it)
    3. Re-upload saved binary from disk to H2O server
    """
    leader = _model_cache.get("leader")
    if leader is not None:
        return leader

    metrics = get_model_metrics()
    model_id = metrics.get("leader_model_id")
    if not model_id or metrics.get("status") == "untrained":
        return None

    from automl.train import init_h2o
    import h2o

    try:
        init_h2o()
    except Exception as e:
        logging.warning(f"[AutoML] Cannot connect to H2O server: {e}")
        return None

    # Strategy 1: Try to fetch model by ID (H2O server may still have it)
    try:
        leader = h2o.get_model(model_id)
        _model_cache["leader"] = leader
        logging.info(f"[AutoML] Reloaded model from H2O server: {model_id}")
        return leader
    except Exception:
        pass

    # Strategy 2: Re-upload saved model binary from disk
    try:
        if os.path.isdir(MODEL_BINARY_DIR):
            model_files = glob.glob(os.path.join(MODEL_BINARY_DIR, "*"))
            if model_files:
                model_path = model_files[0]
                leader = h2o.upload_model(model_path)
                _model_cache["leader"] = leader
                logging.info(f"[AutoML] Re-uploaded model from disk: {model_path}")
                return leader
    except Exception as e:
        logging.warning(f"[AutoML] Could not reload model from disk: {e}")

    logging.warning(f"[AutoML] Model {model_id} unavailable — retrain required")
    return None


def get_model_metrics() -> dict:
    """Get saved model metrics, or status dict if no model."""
    metrics_path = os.path.join(MODEL_SAVE_DIR, "model_metrics.json")
    if os.path.exists(metrics_path):
        with open(metrics_path) as f:
            return json.load(f)
    return {"status": "untrained"}


# In-memory model cache
_model_cache = {}
