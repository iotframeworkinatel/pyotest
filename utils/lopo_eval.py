"""
Leave-One-Protocol-Out (LOPO) Evaluation

Tests whether the ML system generalizes to unseen protocols by:
1. Train on all protocols except one (held-out)
2. Predict on the held-out protocol
3. Compute AUC, Brier, ECE on held-out predictions

This is the key test for out-of-distribution generalization in the
Emergence framework. If the model only memorizes protocol-specific
patterns, LOPO AUC will be near 0.5 (random).
"""
import logging
import os
import tempfile
from typing import Optional

import numpy as np
import pandas as pd

from utils.temporal_eval import compute_temporal_eval


# Default protocols in the IoT lab
PROTOCOLS = ["http", "ftp", "mqtt", "coap", "modbus", "telnet", "dns", "ssh"]


def run_lopo_experiment(
    aggregated_history: str,
    held_out_protocol: str,
    automl_tool: str = "h2o",
    max_runtime_secs: int = 120,
) -> dict:
    """Leave-one-protocol-out evaluation.

    Train on all protocols except held_out, predict on held_out.

    Args:
        aggregated_history: Path to the aggregated history CSV.
        held_out_protocol: Protocol to hold out for evaluation.
        automl_tool: AutoML framework to use for training.
        max_runtime_secs: Training time budget.

    Returns:
        Dict with: held_out, train_protocols, auc, brier, ece, n_train, n_test
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

    full_df["vulnerability_found"] = pd.to_numeric(
        full_df["vulnerability_found"], errors="coerce"
    ).fillna(0).astype(int)

    # Split: train = all protocols except held_out, test = held_out only
    train_df = full_df[full_df["protocol"] != held_out_protocol]
    test_df = full_df[full_df["protocol"] == held_out_protocol]

    result["n_train"] = len(train_df)
    result["n_test"] = len(test_df)
    result["train_protocols"] = sorted(train_df["protocol"].unique().tolist())

    if len(train_df) < 10:
        result["message"] = f"Insufficient training data: {len(train_df)} rows"
        return result

    if len(test_df) < 5:
        result["message"] = f"Insufficient test data for {held_out_protocol}: {len(test_df)} rows"
        return result

    # Need both classes in test set
    if len(test_df["vulnerability_found"].unique()) < 2:
        result["message"] = f"Only one class in test set for {held_out_protocol}"
        result["status"] = "single_class"
        return result

    try:
        from automl.pipeline import train_and_save_model
        from automl.pipeline import get_adapter_for_scoring

        # Write train split to temp file
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, prefix="lopo_train_"
        ) as f:
            train_df.to_csv(f, index=False)
            train_path = f.name

        try:
            # Train on all-but-one protocols
            metrics = train_and_save_model(
                train_path,
                automl_tool=automl_tool,
                max_runtime_secs=max_runtime_secs,
            )

            if metrics.get("status") in ("error", "insufficient_data"):
                result["message"] = f"Training failed: {metrics.get('message', 'unknown')}"
                return result

            # Predict on held-out protocol
            adapter = get_adapter_for_scoring(automl_tool)
            if adapter is None:
                result["message"] = "Could not load trained model for prediction"
                return result

            # Prepare test features
            test_features = test_df.copy()
            test_features["open_port"] = pd.to_numeric(
                test_features["open_port"], errors="coerce"
            ).fillna(0).astype(int)

            if "container_id" in test_features.columns:
                test_features["port_count"] = test_features.groupby("container_id")["open_port"].transform("nunique")
                test_features["protocol_diversity"] = test_features.groupby("container_id")["protocol"].transform("nunique")
            else:
                test_features["port_count"] = 1
                test_features["protocol_diversity"] = 1

            _COMMON_PORTS = {21, 22, 23, 53, 80, 443, 502, 554, 1883, 5683}
            test_features["is_common_port"] = test_features["open_port"].isin(_COMMON_PORTS).astype(int)

            # Get predictions
            pred_df = adapter.predict(test_features)
            if pred_df is not None and "predicted_risk_score" in pred_df.columns:
                scored = test_df.copy()
                scored["predicted_risk_score"] = pred_df["predicted_risk_score"].values

                # Compute metrics using temporal_eval
                eval_result = compute_temporal_eval(scored)

                result["auc_roc"] = eval_result.get("auc_roc")
                result["brier_score"] = eval_result.get("brier_score")
                result["ece"] = eval_result.get("ece")
                result["status"] = "ok"
            else:
                result["message"] = "Prediction did not produce risk scores"

        finally:
            # Clean up temp file
            try:
                os.remove(train_path)
            except OSError:
                pass

    except Exception as e:
        result["message"] = f"LOPO evaluation failed: {e}"
        logging.error(f"[LOPO] Evaluation failed for {held_out_protocol}: {e}")

    return result


def run_all_lopo(
    aggregated_history: str,
    automl_tool: str = "h2o",
    max_runtime_secs: int = 120,
) -> list[dict]:
    """Run LOPO evaluation for all protocols.

    Args:
        aggregated_history: Path to aggregated history CSV.
        automl_tool: Framework to use.
        max_runtime_secs: Training budget per evaluation.

    Returns:
        List of result dicts, one per protocol.
    """
    # Discover available protocols from data
    try:
        df = pd.read_csv(aggregated_history)
        available = sorted(df["protocol"].unique().tolist())
    except Exception:
        available = PROTOCOLS

    results = []
    for protocol in available:
        logging.info(f"[LOPO] Evaluating held-out protocol: {protocol}")
        result = run_lopo_experiment(
            aggregated_history,
            held_out_protocol=protocol,
            automl_tool=automl_tool,
            max_runtime_secs=max_runtime_secs,
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

    aucs = [r["auc_roc"] for r in ok_results if r.get("auc_roc") is not None]
    briers = [r["brier_score"] for r in ok_results if r.get("brier_score") is not None]

    summary = {
        "n_evaluated": len(ok_results),
        "n_protocols": len(results),
        "mean_auc": float(np.mean(aucs)) if aucs else None,
        "std_auc": float(np.std(aucs)) if aucs else None,
        "min_auc": float(np.min(aucs)) if aucs else None,
        "max_auc": float(np.max(aucs)) if aucs else None,
        "mean_brier": float(np.mean(briers)) if briers else None,
    }

    # Verdict based on generalization performance
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
