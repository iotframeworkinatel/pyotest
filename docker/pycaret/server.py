"""
PyCaret REST wrapper — Flask server exposing PyCaret classification pipeline.
"""
import logging
import os
import time

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score, log_loss, accuracy_score, roc_curve

from pycaret.classification import (
    setup as pycaret_setup,
    compare_models,
    predict_model,
    save_model,
    load_model as pycaret_load,
    get_config,
    pull,
)

# Import shared REST framework
import sys
sys.path.insert(0, "/app")
from automl_rest_base import app, register_framework


MODELS_DIR = "/app/models/pycaret"


def train_fn(df, target, config):
    """Train PyCaret classification pipeline."""
    seed = config.get("seed", 42)
    # PyCaret doesn't have a direct time limit — we limit models via n_select
    max_runtime = config.get("max_runtime_secs", 300)

    # Ensure target is integer
    df[target] = df[target].astype(int)

    start = time.time()

    # Initialize PyCaret session
    pycaret_setup(
        data=df,
        target=target,
        session_id=seed,
        verbose=False,
        html=False,
        log_experiment=False,
        n_jobs=-1,
    )

    # Compare models and get the best one
    best_model = compare_models(
        sort="AUC",
        n_select=1,
        budget_time=max_runtime / 60.0,  # PyCaret uses minutes
        verbose=False,
    )

    elapsed = time.time() - start

    metrics = _extract_metrics(best_model, df, target, elapsed)
    return best_model, metrics


def predict_fn(model, df):
    """Predict vulnerability probability using PyCaret."""
    try:
        preds = predict_model(model, data=df, raw_score=True)
        # PyCaret adds prediction_score columns
        score_cols = [c for c in preds.columns if "score" in c.lower() and "1" in str(c)]
        if score_cols:
            return preds[score_cols[0]].tolist()
        # Fallback: look for prediction_score
        if "prediction_score" in preds.columns:
            return preds["prediction_score"].tolist()
        # Last resort: use Score column
        score_col = [c for c in preds.columns if "Score" in c]
        if score_col:
            return preds[score_col[-1]].tolist()
        return preds.iloc[:, -1].tolist()
    except Exception:
        # Fallback to sklearn predict_proba
        proba = model.predict_proba(df)
        return proba[:, 1].tolist()


def save_fn(model, directory):
    """Save PyCaret model."""
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, "pycaret_model")
    save_model(model, path, verbose=False)
    return path


def load_fn(directory):
    """Load PyCaret model from disk."""
    path = os.path.join(directory, "pycaret_model")
    if os.path.exists(path + ".pkl"):
        try:
            return pycaret_load(path, verbose=False)
        except Exception as e:
            logging.warning(f"[PyCaret] Failed to load model: {e}")
    return None


def _extract_metrics(model, df, target, elapsed):
    """Extract metrics from PyCaret best model."""
    metrics = {
        "framework": "pycaret",
        "training_time_secs": round(elapsed, 2),
        "training_rows": len(df),
    }

    try:
        metrics["leader_model_id"] = str(type(model).__name__)
        metrics["leader_algo"] = str(type(model).__name__)
    except Exception:
        metrics["leader_model_id"] = "unknown"
        metrics["leader_algo"] = "unknown"

    # Performance
    try:
        X = df.drop(columns=[target])
        y_true = df[target].astype(int)
        proba = model.predict_proba(X)[:, 1]
        y_pred = (proba >= 0.5).astype(int)

        metrics["auc"] = round(float(roc_auc_score(y_true, proba)), 4)
        metrics["accuracy"] = round(float(accuracy_score(y_true, y_pred)), 4)
        try:
            metrics["logloss"] = round(float(log_loss(y_true, proba)), 4)
        except Exception:
            metrics["logloss"] = None

        fpr, tpr, _ = roc_curve(y_true, proba)
        if len(fpr) > 100:
            step = len(fpr) // 100
            fpr = fpr[::step]
            tpr = tpr[::step]
        metrics["roc_curve"] = {
            "fpr": [round(float(x), 4) for x in fpr],
            "tpr": [round(float(x), 4) for x in tpr],
            "auc": metrics["auc"],
        }
    except Exception as e:
        logging.warning(f"[PyCaret] Could not compute metrics: {e}")
        metrics["auc"] = None

    # Feature importance
    try:
        if hasattr(model, "feature_importances_"):
            fi = model.feature_importances_
            feature_names = list(df.drop(columns=[target]).columns)
            total = fi.sum() if fi.sum() > 0 else 1
            max_fi = fi.max() if fi.max() > 0 else 1
            metrics["feature_importance"] = sorted(
                [
                    {
                        "variable": feature_names[i],
                        "relative_importance": round(float(fi[i]), 4),
                        "scaled_importance": round(float(fi[i] / max_fi), 4),
                        "percentage": round(float(fi[i] / total), 4),
                    }
                    for i in range(len(fi))
                ],
                key=lambda x: x["relative_importance"],
                reverse=True,
            )
    except Exception:
        metrics["feature_importance"] = []

    # Leaderboard from PyCaret compare_models
    try:
        lb = pull()
        if lb is not None and not lb.empty:
            lb_records = []
            for idx, row in lb.head(10).iterrows():
                record = {"model": str(idx)}
                for col in lb.columns:
                    val = row[col]
                    try:
                        record[col] = round(float(val), 6)
                    except (ValueError, TypeError):
                        record[col] = str(val)
                lb_records.append(record)
            metrics["leaderboard"] = lb_records
            metrics["total_models_trained"] = len(lb)
    except Exception:
        metrics["leaderboard"] = []
        metrics["total_models_trained"] = 0

    metrics["cross_validation"] = {"available": False}
    return metrics


register_framework("pycaret", train_fn, predict_fn, save_fn, load_fn)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8083, debug=False)
