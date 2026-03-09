"""
AutoGluon REST wrapper — Flask server exposing AutoGluon TabularPredictor.
"""
import logging
import os
import shutil
import time

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score, log_loss, accuracy_score, roc_curve
from sklearn.model_selection import cross_val_predict

from autogluon.tabular import TabularPredictor

# Import shared REST framework
import sys
sys.path.insert(0, "/app")
from automl_rest_base import app, register_framework


MODELS_DIR = "/app/models/autogluon"


def train_fn(df, target, config):
    """Train AutoGluon TabularPredictor."""
    max_runtime = config.get("max_runtime_secs", 300)
    seed = config.get("seed", 42)

    # Ensure target is categorical
    df[target] = df[target].astype(int).astype(str)

    start = time.time()

    predictor = TabularPredictor(
        label=target,
        eval_metric="roc_auc",
        path=os.path.join(MODELS_DIR, "ag_model"),
    )
    predictor.fit(
        train_data=df,
        time_limit=max_runtime,
        presets="best_quality",
        ag_args_fit={"random_seed": seed},
        verbosity=1,
    )

    elapsed = time.time() - start

    # Extract metrics
    metrics = _extract_metrics(predictor, df, target, elapsed)
    return predictor, metrics


def predict_fn(model, df):
    """Predict vulnerability probability using AutoGluon."""
    proba = model.predict_proba(df)
    # AutoGluon returns a DataFrame with columns for each class
    if "1" in proba.columns:
        return proba["1"].tolist()
    elif 1 in proba.columns:
        return proba[1].tolist()
    else:
        # Take last column as positive class
        return proba.iloc[:, -1].tolist()


def save_fn(model, directory):
    """Save AutoGluon model (it auto-saves to its path)."""
    model_path = model.path
    os.makedirs(directory, exist_ok=True)
    # AutoGluon saves in-place; just return the path
    return model_path


def load_fn(directory):
    """Load AutoGluon model from disk."""
    ag_path = os.path.join(MODELS_DIR, "ag_model")
    if os.path.isdir(ag_path):
        try:
            return TabularPredictor.load(ag_path)
        except Exception as e:
            logging.warning(f"[AutoGluon] Failed to load model: {e}")
    return None


def _extract_metrics(predictor, df, target, elapsed):
    """Extract comprehensive metrics from AutoGluon predictor."""
    metrics = {
        "framework": "autogluon",
        "training_time_secs": round(elapsed, 2),
        "training_rows": len(df),
    }

    try:
        # Best model info
        leader = predictor.get_model_best()
        metrics["leader_model_id"] = str(leader)
        metrics["leader_algo"] = str(type(leader).__name__) if not isinstance(leader, str) else leader
    except Exception:
        metrics["leader_model_id"] = "unknown"
        metrics["leader_algo"] = "unknown"

    # Performance metrics
    try:
        y_true = df[target].astype(int)
        pred_proba = predict_fn(predictor, df.drop(columns=[target]))
        y_pred = [1 if p >= 0.5 else 0 for p in pred_proba]

        metrics["auc"] = round(float(roc_auc_score(y_true, pred_proba)), 4)
        metrics["accuracy"] = round(float(accuracy_score(y_true, y_pred)), 4)
        try:
            metrics["logloss"] = round(float(log_loss(y_true, pred_proba)), 4)
        except Exception:
            metrics["logloss"] = None

        # ROC curve
        fpr, tpr, _ = roc_curve(y_true, pred_proba)
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
        logging.warning(f"[AutoGluon] Could not compute metrics: {e}")
        metrics["auc"] = None

    # Feature importance
    try:
        fi = predictor.feature_importance(df, silent=True)
        if fi is not None and not fi.empty:
            total = fi["importance"].sum() if fi["importance"].sum() > 0 else 1
            metrics["feature_importance"] = [
                {
                    "variable": str(idx),
                    "relative_importance": round(float(row["importance"]), 4),
                    "scaled_importance": round(float(row["importance"] / fi["importance"].max()) if fi["importance"].max() > 0 else 0, 4),
                    "percentage": round(float(row["importance"] / total), 4),
                }
                for idx, row in fi.iterrows()
            ]
    except Exception as e:
        logging.debug(f"[AutoGluon] Could not extract feature importance: {e}")
        metrics["feature_importance"] = []

    # Leaderboard
    try:
        lb = predictor.leaderboard(df, silent=True)
        if lb is not None:
            lb_records = []
            for _, row in lb.head(10).iterrows():
                record = {}
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


# Register and run
register_framework("autogluon", train_fn, predict_fn, save_fn, load_fn)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8082, debug=False)
