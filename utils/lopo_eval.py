"""
Leave-One-Protocol-Out (LOPO) Evaluation

Tests whether the ML system generalizes to unseen protocols by:
1. Train on all protocols except one (held-out)
2. Predict on the held-out protocol
3. Compute AUC, Brier, ECE on held-out predictions

This is the key test for out-of-distribution generalization in the
Emergence framework. If the model only memorizes protocol-specific
patterns, LOPO AUC will be near 0.5 (random).

Implementation note: LOPO folds use sklearn GradientBoostingClassifier
as a consistent cross-framework proxy. This avoids interaction with the
live H2O AutoML cluster (which accumulates memory across sequential
AutoML runs and crashes the API), and ensures that all frameworks are
evaluated with identical methodology. The automl_tool parameter is
retained for data-filtering purposes (Phase 5 per-framework isolation)
but does not affect the LOPO estimator itself.
"""
import logging
import os
from typing import Optional

import numpy as np
import pandas as pd

from utils.temporal_eval import compute_temporal_eval


# Default protocols in the IoT lab
PROTOCOLS = ["http", "ftp", "mqtt", "coap", "modbus", "telnet", "dns", "ssh"]

# Columns that must never appear as LOPO features:
#   - the target itself
#   - free-text / very-high-cardinality identifiers
#   - experiment metadata that would leak train/test assignment
#   - derived columns that duplicate or follow from the target
_LOPO_EXCLUDE = frozenset({
    "vulnerability_found",
    # High-cardinality identifiers — one-hot encoding these creates massive matrices
    "experiment_id", "timestamp",
    "test_id", "test_name", "pytest_code",
    "container_id", "device_name", "exp_dir_name",
    # Experiment metadata / leakage columns
    "automl_tool", "baseline_strategy", "phase",
    "test_strategy", "test_origin", "score_method",
    "simulation_mode", "simulation_seed", "simulation_iteration",
    "is_recommended", "iteration",
})


def _prepare_lopo_features(
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
) -> tuple[np.ndarray, np.ndarray]:
    """Build aligned numeric feature matrices for train and test splits.

    Categorical columns are one-hot encoded on the *combined* dataset so
    that train and test always share the same column layout, even when the
    held-out protocol introduces unseen category values.

    Returns:
        (X_train, X_test) as numpy float32 arrays.
    """
    feature_cols = [c for c in train_df.columns if c not in _LOPO_EXCLUDE]

    X_tr = train_df[feature_cols].copy()
    X_te = test_df[feature_cols].copy()

    cat_cols = [
        c for c in feature_cols
        if X_tr[c].dtype == object or str(X_tr[c].dtype) == "category"
    ]

    if cat_cols:
        n_train = len(X_tr)
        combined = pd.concat([X_tr, X_te], ignore_index=True)
        combined = pd.get_dummies(combined, columns=cat_cols, drop_first=False, dtype=float)
        X_tr = combined.iloc[:n_train].copy()
        X_te = combined.iloc[n_train:].copy()

    X_tr = X_tr.select_dtypes(include=[np.number]).fillna(0)
    X_te = X_te.select_dtypes(include=[np.number]).fillna(0)

    # Align: test may be missing columns that only appeared in train dummies
    X_te = X_te.reindex(columns=X_tr.columns, fill_value=0)

    return X_tr.values.astype(np.float32), X_te.values.astype(np.float32)


def run_lopo_experiment(
    aggregated_history: str,
    held_out_protocol: str,
    automl_tool: str = "h2o",
    max_runtime_secs: int = 60,        # unused — kept for API compat
    full_df: Optional[pd.DataFrame] = None,
) -> dict:
    """Leave-one-protocol-out evaluation using sklearn GBM.

    Trains a GradientBoostingClassifier on all protocols except
    held_out_protocol and evaluates on the held-out split.  Using
    sklearn (rather than the live AutoML adapter) prevents memory
    accumulation in the H2O cluster across many sequential folds.

    Args:
        aggregated_history: Path to the aggregated history CSV.
        held_out_protocol: Protocol to hold out for evaluation.
        automl_tool: Used only for data-filtering context; LOPO always
            uses sklearn GBM for consistent cross-framework evaluation.
        max_runtime_secs: Ignored; kept for backward compatibility.
        full_df: Pre-loaded DataFrame (avoids repeated CSV reads).

    Returns:
        Dict with: held_out, train_protocols, auc_roc, brier_score,
        ece, n_train, n_test, status.
    """
    result = {
        "held_out": held_out_protocol,
        "train_protocols": [],
        "auc_roc": None,
        "brier_score": None,
        "ece": None,
        "n_train": 0,
        "n_test": 0,
        "status": "error",
    }

    if full_df is None:
        if not os.path.exists(aggregated_history):
            result["message"] = f"History file not found: {aggregated_history}"
            return result
        try:
            full_df = pd.read_csv(aggregated_history)
        except Exception as e:
            result["message"] = f"Failed to load history: {e}"
            return result

    if "protocol" not in full_df.columns:
        result["message"] = "No 'protocol' column in history"
        return result

    full_df["vulnerability_found"] = (
        pd.to_numeric(full_df["vulnerability_found"], errors="coerce")
        .fillna(0)
        .astype(int)
    )

    train_df = full_df[full_df["protocol"] != held_out_protocol]
    test_df  = full_df[full_df["protocol"] == held_out_protocol]

    result["n_train"] = len(train_df)
    result["n_test"]  = len(test_df)
    result["train_protocols"] = sorted(train_df["protocol"].unique().tolist())

    if len(train_df) < 10:
        result["message"] = f"Insufficient training data: {len(train_df)} rows"
        return result

    if len(test_df) < 5:
        result["message"] = (
            f"Insufficient test data for {held_out_protocol}: {len(test_df)} rows"
        )
        return result

    if len(test_df["vulnerability_found"].unique()) < 2:
        result["message"] = f"Only one class in test set for {held_out_protocol}"
        result["status"] = "single_class"
        return result

    try:
        from sklearn.ensemble import GradientBoostingClassifier

        X_train, X_test = _prepare_lopo_features(train_df, test_df)
        y_train = train_df["vulnerability_found"].values
        y_test  = test_df["vulnerability_found"].values

        if X_train.shape[1] == 0:
            result["message"] = "No usable feature columns after encoding"
            return result

        clf = GradientBoostingClassifier(
            n_estimators=100,
            max_depth=4,
            learning_rate=0.1,
            subsample=0.8,
            random_state=42,
            n_iter_no_change=10,
            validation_fraction=0.1,
        )
        clf.fit(X_train, y_train)

        proba = clf.predict_proba(X_test)[:, 1]

        scored = test_df.copy()
        scored["predicted_risk_score"] = proba

        eval_result = compute_temporal_eval(scored)

        result["auc_roc"]     = eval_result.get("auc_roc")
        result["brier_score"] = eval_result.get("brier_score")
        result["ece"]         = eval_result.get("ece")
        result["status"]      = "ok"

    except Exception as e:
        result["message"] = f"LOPO evaluation failed: {e}"
        logging.error(f"[LOPO] Evaluation failed for {held_out_protocol}: {e}")

    return result


def run_all_lopo(
    aggregated_history: str,
    automl_tool: str = "h2o",
    max_runtime_secs: int = 60,
    max_rows: int = 50_000,
) -> list[dict]:
    """Run LOPO evaluation for all protocols.

    Loads the CSV once and optionally samples it to keep training fast.

    Args:
        aggregated_history: Path to aggregated history CSV.
        automl_tool: Passed through to run_lopo_experiment for context.
        max_runtime_secs: Passed through (unused by sklearn path).
        max_rows: Cap on total rows (stratified sample if exceeded).

    Returns:
        List of result dicts, one per protocol.
    """
    try:
        df = pd.read_csv(aggregated_history)
    except Exception:
        return []

    if df.empty or "protocol" not in df.columns:
        return []

    # Stratified sample to keep per-fold training fast.
    # Explicit loop avoids pandas FutureWarning on groupby.apply.
    if len(df) > max_rows:
        logging.info(f"[LOPO] Sampling {max_rows} rows from {len(df)} for performance")
        total = len(df)
        sampled = []
        for _, group in df.groupby("protocol"):
            n = min(len(group), max(10, int(max_rows * len(group) / total)))
            sampled.append(group.sample(n, random_state=42))
        df = pd.concat(sampled, ignore_index=True)

    available = sorted(df["protocol"].unique().tolist())

    results = []
    for protocol in available:
        logging.info(f"[LOPO] Evaluating held-out protocol: {protocol}")
        result = run_lopo_experiment(
            aggregated_history,
            held_out_protocol=protocol,
            automl_tool=automl_tool,
            max_runtime_secs=max_runtime_secs,
            full_df=df,
        )
        results.append(result)
        logging.info(
            f"[LOPO] {protocol}: AUC={result.get('auc_roc', 'N/A')}, "
            f"Brier={result.get('brier_score', 'N/A')}, "
            f"n_test={result.get('n_test', 0)}"
        )

    return results


def lopo_summary(results: list[dict]) -> dict:
    """Compute summary statistics from LOPO results.

    Args:
        results: List of per-protocol LOPO result dicts.

    Returns:
        Summary dict with mean/std metrics and verdict.
    """
    ok_results = [r for r in results if r.get("status") == "ok"]

    if not ok_results:
        return {
            "n_evaluated": 0,
            "n_protocols": len(results),
            "mean_auc": None,
            "verdict": "insufficient_data",
        }

    aucs   = [r["auc_roc"]     for r in ok_results if r.get("auc_roc")     is not None]
    briers = [r["brier_score"] for r in ok_results if r.get("brier_score") is not None]

    summary = {
        "n_evaluated": len(ok_results),
        "n_protocols": len(results),
        "mean_auc":  float(np.mean(aucs))   if aucs   else None,
        "std_auc":   float(np.std(aucs))    if aucs   else None,
        "min_auc":   float(np.min(aucs))    if aucs   else None,
        "max_auc":   float(np.max(aucs))    if aucs   else None,
        "mean_brier": float(np.mean(briers)) if briers else None,
    }

    mean_auc = summary.get("mean_auc")
    if mean_auc is not None and mean_auc > 0.65:
        summary["verdict"] = "generalizes"
    elif mean_auc is not None and mean_auc > 0.55:
        summary["verdict"] = "partial_generalization"
    elif mean_auc is not None:
        summary["verdict"] = "does_not_generalize"
    else:
        summary["verdict"] = "insufficient_data"

    return summary
