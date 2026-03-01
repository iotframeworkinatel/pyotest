"""
Model Retraining — called after test suite execution to improve the ML model.
"""
import logging
import os
import glob

from automl.pipeline import train_and_save_model


def retrain_model_after_execution(history_csv_path: str) -> dict:
    """
    Retrain the H2O model after a test suite execution.
    Uses the specified history CSV (or aggregates all history).

    Returns model metrics dict or error status.
    """
    if not os.path.exists(history_csv_path):
        logging.warning(f"[Retrain] History file not found: {history_csv_path}")
        return {"status": "error", "message": "History file not found"}

    try:
        metrics = train_and_save_model(history_csv_path)
        logging.info(f"[Retrain] Model retrained successfully: AUC={metrics.get('auc', '?')}")
        return metrics
    except Exception as e:
        logging.error(f"[Retrain] Failed to retrain model: {e}")
        return {"status": "error", "message": str(e)}


def find_all_history_files(base_dir: str = "experiments") -> list[str]:
    """Find all history.csv files across experiment directories."""
    pattern = os.path.join(base_dir, "exp_*", "history.csv")
    return sorted(glob.glob(pattern))


def aggregate_history(base_dir: str = "experiments") -> str:
    """
    Aggregate all history.csv files into a single file for training.
    Returns path to the aggregated file.
    """
    import pandas as pd

    history_files = find_all_history_files(base_dir)
    if not history_files:
        return ""

    dfs = []
    for f in history_files:
        try:
            df = pd.read_csv(f)
            dfs.append(df)
        except Exception as e:
            logging.debug(f"[Retrain] Skipping {f}: {e}")

    if not dfs:
        return ""

    combined = pd.concat(dfs, ignore_index=True)
    output_path = os.path.join(base_dir, "aggregated_history.csv")
    combined.to_csv(output_path, index=False)

    logging.info(f"[Retrain] Aggregated {len(history_files)} history files ({len(combined)} rows)")
    return output_path
