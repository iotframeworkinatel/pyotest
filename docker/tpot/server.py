"""
TPOT REST wrapper — Flask server exposing TPOT genetic programming AutoML.
"""
import logging
import os
import pickle
import time

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score, log_loss, accuracy_score, roc_curve
from sklearn.model_selection import cross_val_predict

from tpot import TPOTClassifier

# Import shared REST framework
import sys
sys.path.insert(0, "/app")
from automl_rest_base import app, register_framework


MODELS_DIR = "/app/models/tpot"


def train_fn(df, target, config):
    """Train TPOT genetic programming pipeline."""
    max_runtime = config.get("max_runtime_secs", 300)
    seed = config.get("seed", 42)

    # Prepare data — TPOT needs numeric features
    df[target] = df[target].astype(int)
    X = df.drop(columns=[target])
    y = df[target]

    # Encode string/categorical columns
    cat_cols = X.select_dtypes(include=["object", "category"]).columns
    if len(cat_cols) > 0:
        X = pd.get_dummies(X, columns=cat_cols, drop_first=True)

    start = time.time()

    tpot = TPOTClassifier(
        max_time_mins=max(1, max_runtime // 60),
        random_state=seed,
        verbosity=1,
        n_jobs=-1,
        cv=5,
    )
    tpot.fit(X.values, y.values)

    elapsed = time.time() - start

    # Store column info for prediction time
    tpot._emergence_columns = list(X.columns)
    tpot._emergence_cat_cols = list(cat_cols)

    metrics = _extract_metrics(tpot, X, y, elapsed, len(df))
    return tpot, metrics


def predict_fn(model, df):
    """Predict vulnerability probability using TPOT."""
    # Encode categoricals same way as training
    cat_cols = getattr(model, "_emergence_cat_cols", [])
    train_cols = getattr(model, "_emergence_columns", [])

    if cat_cols:
        existing_cats = [c for c in cat_cols if c in df.columns]
        if existing_cats:
            df = pd.get_dummies(df, columns=existing_cats, drop_first=True)

    # Align columns with training
    if train_cols:
        for col in train_cols:
            if col not in df.columns:
                df[col] = 0
        df = df[train_cols]

    proba = model.predict_proba(df.values)
    return proba[:, 1].tolist()


def save_fn(model, directory):
    """Save TPOT model."""
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, "tpot_model.pkl")
    with open(path, "wb") as f:
        pickle.dump(model, f)

    # Also export the Python pipeline
    try:
        pipeline_path = os.path.join(directory, "tpot_pipeline.py")
        model.export(pipeline_path)
    except Exception:
        pass

    return path


def load_fn(directory):
    """Load TPOT model from disk."""
    path = os.path.join(directory, "tpot_model.pkl")
    if os.path.exists(path):
        try:
            with open(path, "rb") as f:
                return pickle.load(f)
        except Exception as e:
            logging.warning(f"[TPOT] Failed to load model: {e}")
    return None


def _extract_metrics(tpot, X, y, elapsed, training_rows):
    """Extract metrics from TPOT pipeline."""
    metrics = {
        "framework": "tpot",
        "training_time_secs": round(elapsed, 2),
        "training_rows": training_rows,
    }

    try:
        best = tpot.fitted_pipeline_
        metrics["leader_model_id"] = str(best)[:100]
        # Get the last step's class name
        if hasattr(best, "steps"):
            metrics["leader_algo"] = type(best.steps[-1][1]).__name__
        else:
            metrics["leader_algo"] = type(best).__name__
    except Exception:
        metrics["leader_model_id"] = "unknown"
        metrics["leader_algo"] = "unknown"

    # Performance
    try:
        proba = tpot.predict_proba(X.values)[:, 1]
        y_pred = (proba >= 0.5).astype(int)

        metrics["auc"] = round(float(roc_auc_score(y, proba)), 4)
        metrics["accuracy"] = round(float(accuracy_score(y, y_pred)), 4)
        try:
            metrics["logloss"] = round(float(log_loss(y, proba)), 4)
        except Exception:
            metrics["logloss"] = None

        fpr, tpr, _ = roc_curve(y, proba)
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
        logging.warning(f"[TPOT] Could not compute metrics: {e}")
        metrics["auc"] = None

    # Feature importance (if available from the fitted pipeline)
    try:
        best_model = tpot.fitted_pipeline_
        # Try to get feature importance from last estimator
        if hasattr(best_model, "steps"):
            last_step = best_model.steps[-1][1]
        else:
            last_step = best_model

        if hasattr(last_step, "feature_importances_"):
            fi = last_step.feature_importances_
            feature_names = list(X.columns)
            if len(fi) == len(feature_names):
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

    # TPOT leaderboard (evaluated pipelines)
    try:
        if hasattr(tpot, "evaluated_individuals_"):
            lb_items = sorted(
                tpot.evaluated_individuals_.items(),
                key=lambda x: x[1].get("internal_cv_score", 0),
                reverse=True,
            )[:10]
            metrics["leaderboard"] = [
                {
                    "model_id": str(name)[:80],
                    "cv_score": round(float(info.get("internal_cv_score", 0)), 6),
                }
                for name, info in lb_items
            ]
            metrics["total_models_trained"] = len(tpot.evaluated_individuals_)
    except Exception:
        metrics["leaderboard"] = []
        metrics["total_models_trained"] = 0

    metrics["cross_validation"] = {"available": True}
    # CV score from TPOT's internal evaluation
    try:
        cv_score = tpot.score(X.values, y.values)
        metrics["cv_auc"] = round(float(cv_score), 4)
    except Exception:
        pass

    return metrics


register_framework("tpot", train_fn, predict_fn, save_fn, load_fn)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8084, debug=False)
