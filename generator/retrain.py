"""
Model Retraining — called after test suite execution to improve the ML model.

Supports multiple AutoML frameworks via the ``automl_tool`` parameter.
Defaults to H2O for backward compatibility.
"""
import logging
import os
import glob

from automl.pipeline import train_and_save_model


def retrain_model_after_execution(
    history_csv_path: str,
    automl_tool: str = "h2o",
) -> dict:
    """
    Retrain the selected AutoML model after a test suite execution.
    Uses the specified history CSV (or aggregates all history).

    Args:
        history_csv_path: Path to the history CSV file.
        automl_tool: Framework name (h2o, autogluon, pycaret, tpot, autosklearn).

    Returns model metrics dict or error status.
    """
    if not os.path.exists(history_csv_path):
        logging.warning(f"[Retrain] History file not found: {history_csv_path}")
        return {"status": "error", "message": "History file not found"}

    try:
        metrics = train_and_save_model(history_csv_path, automl_tool=automl_tool)
        logging.info(
            f"[Retrain:{automl_tool}] Model retrained successfully: "
            f"AUC={metrics.get('auc', '?')}"
        )
        return metrics
    except Exception as e:
        logging.error(f"[Retrain:{automl_tool}] Failed to retrain model: {e}")
        return {"status": "error", "message": str(e)}


def retrain_all_frameworks(
    history_csv_path: str,
    frameworks: list[str] = None,
) -> dict[str, dict]:
    """
    Retrain multiple AutoML frameworks on the same history data.

    Args:
        history_csv_path: Path to the history CSV file.
        frameworks: List of framework names. If None, uses all registered.

    Returns dict keyed by framework name with metrics for each.
    """
    if frameworks is None:
        from automl.registry import list_available
        frameworks = list_available()

    results = {}
    for fw in frameworks:
        logging.info(f"[Retrain] Training {fw}...")
        results[fw] = retrain_model_after_execution(history_csv_path, automl_tool=fw)
    return results


def find_all_history_files(base_dir: str = "experiments") -> list[str]:
    """Find all history.csv files across experiment directories."""
    pattern = os.path.join(base_dir, "exp_*", "history.csv")
    return sorted(glob.glob(pattern))


def aggregate_history(base_dir: str = "experiments", simulation_mode: str = None) -> str:
    """
    Aggregate history.csv files into a single file for training.

    Args:
        base_dir: Base experiments directory.
        simulation_mode: If provided, only include rows matching this mode.
            The output file is named ``aggregated_history_{mode}.csv`` so
            that different simulation experiments never contaminate each
            other's training data.  When *None*, all rows are aggregated
            into ``aggregated_history.csv`` (legacy behaviour).

    Returns path to the aggregated file, or "" if no data.
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

    # Filter to the requested simulation mode
    if simulation_mode and "simulation_mode" in combined.columns:
        combined = combined[combined["simulation_mode"] == simulation_mode]
        if combined.empty:
            logging.warning(f"[Retrain] No rows for simulation_mode={simulation_mode}")
            return ""
        suffix = f"_{simulation_mode}"
    else:
        suffix = ""

    output_path = os.path.join(base_dir, f"aggregated_history{suffix}.csv")
    combined.to_csv(output_path, index=False)

    logging.info(
        f"[Retrain] Aggregated {len(history_files)} history files "
        f"({len(combined)} rows, mode={simulation_mode or 'all'}) -> {output_path}"
    )
    return output_path
