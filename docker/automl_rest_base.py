"""
Shared AutoML REST wrapper — Flask server that exposes a unified API for any
scikit-learn-compatible AutoML framework.

Each framework's server.py imports this module and registers its train/predict
implementation. The REST API contract is:

    POST /train    — Train model on CSV data
    POST /predict  — Predict risk scores for CSV features
    GET  /status   — Health check / model status
    GET  /metrics  — Return saved model metrics
    POST /save     — Persist model to disk
    POST /load     — Load model from disk
"""
import io
import json
import logging
import math
import os
import traceback

import numpy as np
import pandas as pd
from flask import Flask, request, jsonify

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

app = Flask(__name__)

# ── Framework implementation registry ────────────────────────────────────
_impl = {
    "train_fn": None,        # (df, target, config) -> (model, metrics_dict)
    "predict_fn": None,      # (model, df) -> list[float]  (p1 probabilities)
    "save_fn": None,         # (model, directory) -> str  (saved path)
    "load_fn": None,         # (directory) -> model or None
    "framework_name": "unknown",
}

_state = {
    "model": None,
    "metrics": None,
    "ready": True,
}


def register_framework(
    name: str,
    train_fn,
    predict_fn,
    save_fn,
    load_fn,
):
    """Register framework-specific functions."""
    _impl["framework_name"] = name
    _impl["train_fn"] = train_fn
    _impl["predict_fn"] = predict_fn
    _impl["save_fn"] = save_fn
    _impl["load_fn"] = load_fn


def _sanitize(obj):
    """Recursively replace NaN/inf with None for JSON safety."""
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_sanitize(v) for v in obj]
    elif isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    elif isinstance(obj, (np.floating,)):
        v = float(obj)
        if math.isnan(v) or math.isinf(v):
            return None
        return v
    elif isinstance(obj, (np.integer,)):
        return int(obj)
    elif isinstance(obj, np.bool_):
        return bool(obj)
    elif isinstance(obj, np.ndarray):
        return _sanitize(obj.tolist())
    return obj


# ═══════════════════════════════════════════════════════════════════════
# REST ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════

@app.route("/status", methods=["GET"])
def status():
    return jsonify({
        "ready": _state["ready"],
        "framework": _impl["framework_name"],
        "model_loaded": _state["model"] is not None,
    })


@app.route("/metrics", methods=["GET"])
def metrics():
    if _state["metrics"]:
        return jsonify(_sanitize(_state["metrics"]))
    return jsonify({"status": "untrained"})


@app.route("/train", methods=["POST"])
def train():
    try:
        data = request.json
        csv_data = data.get("csv_data", "")
        target = data.get("target", "vulnerability_found")
        max_runtime_secs = data.get("max_runtime_secs", 300)
        seed = data.get("seed", 42)

        if not csv_data:
            return jsonify({"error": "No csv_data provided"}), 400

        df = pd.read_csv(io.StringIO(csv_data))
        logging.info(
            f"[{_impl['framework_name']}] Training on {len(df)} rows, "
            f"target={target}, max_runtime={max_runtime_secs}s"
        )

        config = {
            "max_runtime_secs": max_runtime_secs,
            "seed": seed,
        }

        model, metrics_dict = _impl["train_fn"](df, target, config)

        _state["model"] = model
        _state["metrics"] = metrics_dict

        logging.info(
            f"[{_impl['framework_name']}] Training complete — "
            f"AUC: {metrics_dict.get('auc', '?')}"
        )

        return jsonify(_sanitize(metrics_dict))

    except Exception as e:
        logging.error(f"[{_impl['framework_name']}] Training error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/predict", methods=["POST"])
def predict():
    try:
        data = request.json
        csv_data = data.get("csv_data", "")

        if not csv_data:
            return jsonify({"error": "No csv_data provided"}), 400

        if _state["model"] is None:
            return jsonify({"error": "No model loaded. Train first."}), 400

        df = pd.read_csv(io.StringIO(csv_data))
        predictions = _impl["predict_fn"](_state["model"], df)

        return jsonify({"predictions": [float(p) for p in predictions]})

    except Exception as e:
        logging.error(f"[{_impl['framework_name']}] Predict error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/save", methods=["POST"])
def save():
    try:
        data = request.json
        directory = data.get("directory", "/app/models")

        if _state["model"] is None:
            return jsonify({"error": "No model to save"}), 400

        path = _impl["save_fn"](_state["model"], directory)
        return jsonify({"path": path, "saved": True})

    except Exception as e:
        logging.error(f"[{_impl['framework_name']}] Save error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/load", methods=["POST"])
def load():
    try:
        data = request.json
        directory = data.get("directory", "/app/models")

        model = _impl["load_fn"](directory)
        if model is not None:
            _state["model"] = model
            return jsonify({"loaded": True})
        return jsonify({"loaded": False, "error": "No saved model found"})

    except Exception as e:
        logging.error(f"[{_impl['framework_name']}] Load error: {e}")
        return jsonify({"error": str(e)}), 500
