"""
auto-sklearn REST wrapper — Flask server exposing auto-sklearn AutoML.

Note: auto-sklearn requires Linux and specific system libraries.
It uses Bayesian optimization for hyperparameter tuning and ensemble selection.
"""
import logging
import os
import pickle
import time

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score, log_loss, accuracy_score, roc_curve

import autosklearn.classification

# Import shared REST framework
import sys
sys.path.insert(0, "/app")
from automl_rest_base import app, register_framework


MODELS_DIR = "/app/models/autosklearn"


def train_fn(df, target, config):
    """Train auto-sklearn classifier."""
    max_runtime = config.get("max_runtime_secs", 300)
    seed = config.get("seed", 42)

    # Prepare data — auto-sklearn works with numpy/pandas
    df[target] = df[target].astype(int)
    X = df.drop(columns=[target])
    y = df[target]

    # Encode string/categorical columns
    cat_cols = X.select_dtypes(include=["object", "category"]).columns.tolist()
    if cat_cols:
        X = pd.get_dummies(X, columns=cat_cols, drop_first=True)

    start = time.time()

    automl = autosklearn.classification.AutoSklearnClassifier(
        time_left_for_this_task=max_runtime,
        per_run_time_limit=max(60, max_runtime // 5),  # was max_runtime//10 — too tight
        seed=seed,
        n_jobs=-1,
        memory_limit=4096,
        resampling_strategy="holdout",               # was "cv" — 5-fold CV exhausts budget
        resampling_strategy_arguments={"train_size": 0.8},
        metric=autosklearn.metrics.roc_auc,
        tmp_folder=os.path.join(MODELS_DIR, "tmp"),
    )
    automl.fit(X, y)

    # Refit on full dataset
    automl.refit(X, y)

    elapsed = time.time() - start

    # Store column info
    automl._emergence_columns = list(X.columns)
    automl._emergence_cat_cols = cat_cols

    metrics = _extract_metrics(automl, X, y, elapsed, len(df))
    return automl, metrics


def predict_fn(model, df):
    """Predict vulnerability probability using auto-sklearn."""
    cat_cols = getattr(model, "_emergence_cat_cols", [])
    train_cols = getattr(model, "_emergence_columns", [])

    if cat_cols:
        existing_cats = [c for c in cat_cols if c in df.columns]
        if existing_cats:
            df = pd.get_dummies(df, columns=existing_cats, drop_first=True)

    if train_cols:
        for col in train_cols:
            if col not in df.columns:
                df[col] = 0
        df = df[train_cols]

    proba = model.predict_proba(df)
    return proba[:, 1].tolist()


def save_fn(model, directory):
    """Save auto-sklearn model."""
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, "autosklearn_model.pkl")
    with open(path, "wb") as f:
        pickle.dump(model, f)
    return path


def load_fn(directory):
    """Load auto-sklearn model from disk."""
    path = os.path.join(directory, "autosklearn_model.pkl")
    if os.path.exists(path):
        try:
            with open(path, "rb") as f:
                return pickle.load(f)
        except Exception as e:
            logging.warning(f"[auto-sklearn] Failed to load model: {e}")
    return None


def _extract_metrics(automl, X, y, elapsed, training_rows):
    """Extract metrics from auto-sklearn."""
    metrics = {
        "framework": "autosklearn",
        "training_time_secs": round(elapsed, 2),
        "training_rows": training_rows,
    }

    # Best model info
    try:
        stats = automl.sprint_statistics()
        metrics["leader_model_id"] = "auto-sklearn-ensemble"

        # Get the best model type from the ensemble
        show = automl.show_models()
        if show:
            first_key = list(show.keys())[0]
            first_model = show[first_key]
            algo_name = first_model.get("classifier:__choice__", "unknown")
            metrics["leader_algo"] = str(algo_name)
        else:
            metrics["leader_algo"] = "ensemble"
    except Exception:
        metrics["leader_model_id"] = "unknown"
        metrics["leader_algo"] = "unknown"

    # Performance
    try:
        proba = automl.predict_proba(X)[:, 1]
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
        logging.warning(f"[auto-sklearn] Could not compute metrics: {e}")
        metrics["auc"] = None

    # Feature importance is not directly available from auto-sklearn ensembles
    metrics["feature_importance"] = []

    # Leaderboard from auto-sklearn models
    try:
        show = automl.show_models()
        if show:
            lb_records = []
            for idx, (model_id, model_info) in enumerate(list(show.items())[:10]):
                record = {
                    "model_id": str(model_id),
                    "weight": round(float(model_info.get("ensemble_weight", 0)), 6),
                    "cost": round(float(model_info.get("cost", 0)), 6),
                    "classifier": str(model_info.get("classifier:__choice__", "?")),
                }
                lb_records.append(record)
            metrics["leaderboard"] = lb_records
            metrics["total_models_trained"] = len(show)
    except Exception:
        metrics["leaderboard"] = []
        metrics["total_models_trained"] = 0

    # CV info
    try:
        cv_results = automl.cv_results_
        if cv_results and "mean_test_score" in cv_results:
            best_idx = np.argmax(cv_results["mean_test_score"])
            metrics["cv_auc"] = round(float(cv_results["mean_test_score"][best_idx]), 4)
            metrics["cross_validation"] = {"available": True}
    except Exception:
        metrics["cross_validation"] = {"available": False}

    return metrics


register_framework("autosklearn", train_fn, predict_fn, save_fn, load_fn)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8085, debug=False)
