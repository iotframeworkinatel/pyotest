"""
Temporal Train/Test Evaluation Utilities

Provides held-out evaluation metrics for expanding-window temporal validation.
The key idea: train on iterations 1..k, predict on iteration k+1, compute
metrics only on the held-out iteration. This prevents the circularity of
evaluating a model on the same data it was trained on.
"""
import logging
import os
from typing import Optional

import numpy as np
import pandas as pd


def compute_temporal_eval(
    scored_df: pd.DataFrame,
    train_window_size: int = 0,
) -> dict:
    """Compute held-out evaluation metrics for temporal validation.

    Args:
        scored_df: DataFrame with columns 'vulnerability_found' (0/1) and
            'predicted_risk_score' (float 0-1).
        train_window_size: Number of training iterations used (for metadata).

    Returns:
        Dict with: auc_roc, brier_score, ece, mce, n_samples, train_window_size
        Returns None-valued metrics if insufficient data.
    """
    result = {
        "auc_roc": None,
        "brier_score": None,
        "ece": None,
        "mce": None,
        "n_samples": 0,
        "train_window_size": train_window_size,
    }

    if scored_df is None or scored_df.empty:
        return result

    if "predicted_risk_score" not in scored_df.columns:
        return result

    y_true = scored_df["vulnerability_found"].values.astype(int)
    y_score = scored_df["predicted_risk_score"].values.astype(float)

    # Filter out NaN scores
    valid_mask = ~np.isnan(y_score) & ~np.isnan(y_true.astype(float))
    y_true = y_true[valid_mask]
    y_score = y_score[valid_mask]

    result["n_samples"] = int(len(y_true))

    if len(y_true) < 5:
        return result

    # Need both classes for AUC
    n_pos = int(y_true.sum())
    n_neg = int(len(y_true) - n_pos)

    # AUC-ROC
    if n_pos >= 1 and n_neg >= 1:
        try:
            from sklearn.metrics import roc_auc_score
            result["auc_roc"] = float(roc_auc_score(y_true, y_score))
        except Exception as e:
            logging.debug(f"[TemporalEval] AUC failed: {e}")

    # Brier score: mean((predicted - actual)^2)
    try:
        result["brier_score"] = float(np.mean((y_score - y_true) ** 2))
    except Exception as e:
        logging.debug(f"[TemporalEval] Brier score failed: {e}")

    # Expected Calibration Error (ECE) and Maximum Calibration Error (MCE)
    try:
        ece, mce = _calibration_error(y_true, y_score, n_bins=10)
        result["ece"] = ece
        result["mce"] = mce
    except Exception as e:
        logging.debug(f"[TemporalEval] ECE failed: {e}")

    return result


def _calibration_error(y_true: np.ndarray, y_score: np.ndarray, n_bins: int = 10):
    """Compute ECE and MCE using equal-width binning."""
    bin_edges = np.linspace(0, 1, n_bins + 1)
    ece = 0.0
    mce = 0.0
    total = len(y_true)

    for i in range(n_bins):
        mask = (y_score >= bin_edges[i]) & (y_score < bin_edges[i + 1])
        if i == n_bins - 1:  # Include right edge in last bin
            mask = mask | (y_score == bin_edges[i + 1])

        n_bin = mask.sum()
        if n_bin == 0:
            continue

        avg_predicted = float(y_score[mask].mean())
        avg_actual = float(y_true[mask].mean())
        bin_error = abs(avg_predicted - avg_actual)

        ece += (n_bin / total) * bin_error
        mce = max(mce, bin_error)

    return float(ece), float(mce)


def filter_temporal_train(
    df: pd.DataFrame,
    train_iterations: range,
    iteration_col: str = "simulation_iteration",
) -> pd.DataFrame:
    """Filter DataFrame to only include rows from the specified training iterations.

    Args:
        df: Full history DataFrame.
        train_iterations: Range of iterations to include in training set.
        iteration_col: Column name for iteration number.

    Returns:
        Filtered DataFrame (copy).
    """
    if iteration_col not in df.columns:
        logging.warning(f"[TemporalEval] Column '{iteration_col}' not found in DataFrame")
        return df.copy()

    mask = df[iteration_col].isin(list(train_iterations))
    return df[mask].copy()


def filter_temporal_test(
    df: pd.DataFrame,
    test_iteration: int,
    iteration_col: str = "simulation_iteration",
) -> pd.DataFrame:
    """Filter DataFrame to only include rows from the specified test iteration.

    Args:
        df: Full history DataFrame.
        test_iteration: The held-out iteration number.
        iteration_col: Column name for iteration number.

    Returns:
        Filtered DataFrame (copy).
    """
    if iteration_col not in df.columns:
        logging.warning(f"[TemporalEval] Column '{iteration_col}' not found in DataFrame")
        return pd.DataFrame()

    mask = df[iteration_col] == test_iteration
    return df[mask].copy()


def save_temporal_metrics(
    metrics_list: list[dict],
    output_path: str,
) -> None:
    """Save temporal metrics to a CSV file.

    Args:
        metrics_list: List of metric dicts from compute_temporal_eval().
        output_path: Path to write CSV.
    """
    if not metrics_list:
        return

    df = pd.DataFrame(metrics_list)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    df.to_csv(output_path, index=False)
    logging.info(f"[TemporalEval] Saved {len(metrics_list)} temporal metrics to {output_path}")


def load_temporal_metrics(csv_path: str) -> Optional[pd.DataFrame]:
    """Load temporal metrics from CSV.

    Returns DataFrame or None if file doesn't exist.
    """
    if not os.path.exists(csv_path):
        return None
    try:
        return pd.read_csv(csv_path)
    except Exception as e:
        logging.warning(f"[TemporalEval] Failed to load {csv_path}: {e}")
        return None
