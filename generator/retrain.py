"""
Model Retraining — called after test suite execution to improve the ML model.

Supports multiple AutoML frameworks via the ``automl_tool`` parameter.
Defaults to H2O for backward compatibility.

Includes temporal retraining support: ``retrain_model_temporal()`` trains
only on past iterations (expanding window) for proper held-out evaluation.
"""
import logging
import os
import glob

import pandas as pd

from automl.pipeline import train_and_save_model


def retrain_model_after_execution(
    history_csv_path: str,
    automl_tool: str = "h2o",
    dynamic: bool = False,
) -> dict:
    """
    Retrain the selected AutoML model after a test suite execution.
    Uses the specified history CSV (or aggregates all history).

    Args:
        history_csv_path: Path to the history CSV file.
        automl_tool: Framework name (h2o, autogluon, pycaret, tpot, autosklearn).
        dynamic: If True, compute rolling temporal features (Phase 5/6).

    Returns model metrics dict or error status.
    """
    if not os.path.exists(history_csv_path):
        logging.warning(f"[Retrain] History file not found: {history_csv_path}")
        return {"status": "error", "message": "History file not found"}

    try:
        metrics = train_and_save_model(history_csv_path, automl_tool=automl_tool,
                                       dynamic=dynamic)
        logging.info(
            f"[Retrain:{automl_tool}] Model retrained successfully: "
            f"AUC={metrics.get('auc', '?')}"
        )
        return metrics
    except Exception as e:
        logging.error(f"[Retrain:{automl_tool}] Failed to retrain model: {e}")
        return {"status": "error", "message": str(e)}


def retrain_model_temporal(
    history_csv_path: str,
    current_iteration: int,
    train_iterations: range,
    automl_tool: str = "h2o",
    max_runtime_secs: int = 300,
    dynamic: bool = False,
) -> dict:
    """
    Retrain model using only data from past iterations (expanding window).

    This enables proper temporal validation: train on iterations 1..k,
    then evaluate on iteration k+1. The model never sees future data.

    Args:
        history_csv_path: Path to the aggregated history CSV.
        current_iteration: The current iteration number (for logging).
        train_iterations: Range of iterations to include in training.
            E.g., range(1, k) trains on iterations 1 through k-1.
        automl_tool: Framework name.
        max_runtime_secs: Training time budget.

    Returns:
        Model metrics dict with added 'train_window' field, or error status.
    """
    if not os.path.exists(history_csv_path):
        logging.warning(f"[Retrain:temporal] History file not found: {history_csv_path}")
        return {"status": "error", "message": "History file not found"}

    try:
        # Load full history and filter to training window
        full_df = pd.read_csv(history_csv_path)

        if "simulation_iteration" not in full_df.columns:
            logging.warning("[Retrain:temporal] No simulation_iteration column — "
                            "falling back to full retrain")
            return retrain_model_after_execution(history_csv_path, automl_tool)

        train_iters = list(train_iterations)
        train_df = full_df[full_df["simulation_iteration"].isin(train_iters)]

        if len(train_df) < 10:
            logging.warning(
                f"[Retrain:temporal] Insufficient training data: "
                f"{len(train_df)} rows from iterations {train_iters[:3]}..{train_iters[-1:]}"
            )
            return {
                "status": "insufficient_data",
                "rows": len(train_df),
                "train_window": [min(train_iters), max(train_iters)] if train_iters else [],
            }

        # Write filtered training data to a temporary file
        train_csv = history_csv_path.replace(".csv", f"_temporal_train.csv")
        train_df.to_csv(train_csv, index=False)

        # Train the model on the filtered data
        metrics = train_and_save_model(
            train_csv,
            automl_tool=automl_tool,
            max_runtime_secs=max_runtime_secs,
            dynamic=dynamic,
        )

        # Add temporal metadata
        metrics["train_window"] = [min(train_iters), max(train_iters)]
        metrics["train_iterations_count"] = len(train_iters)
        metrics["train_rows"] = len(train_df)
        metrics["current_iteration"] = current_iteration

        logging.info(
            f"[Retrain:temporal:{automl_tool}] Model trained on iterations "
            f"{min(train_iters)}-{max(train_iters)} ({len(train_df)} rows), "
            f"AUC={metrics.get('auc', '?')}"
        )

        # Clean up temporary file
        try:
            os.remove(train_csv)
        except OSError:
            pass

        return metrics

    except Exception as e:
        logging.error(f"[Retrain:temporal:{automl_tool}] Failed: {e}")
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


def aggregate_history(base_dir: str = "experiments", simulation_mode: str = None,
                      automl_tool: str = None, phase_tag: str = None,
                      seed: int = None) -> str:
    """
    Aggregate history.csv files into a single file for training.

    Args:
        base_dir: Base experiments directory.
        simulation_mode: If provided, only include rows matching this mode.
            The output file is named ``aggregated_history_{mode}.csv`` so
            that different simulation experiments never contaminate each
            other's training data.  When *None*, all rows are aggregated
            into ``aggregated_history.csv`` (legacy behaviour).
        automl_tool: If provided, only include rows matching this framework.
            Prevents cross-framework contamination where later frameworks
            would train on data from earlier frameworks' experiments.
        phase_tag: If provided, only include rows matching this phase label
            (e.g. "phase5", "phase6"). This is the primary leakage-prevention
            mechanism between Phase 1 (static features) and Phase 5/6
            (dynamic features) — models for each phase must only train on
            their own phase's data.
        seed: If provided, only include rows matching this simulation seed.
            Prevents cross-seed contamination when multiple seeds of the same
            mode run in the same experiments directory (e.g. realistic seed=42,
            seed=123, seed=777 for robustness testing).

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

    # Filter to the requested automl framework to prevent cross-framework
    # contamination (each framework should only train on its own data)
    if automl_tool and "automl_tool" in combined.columns:
        combined = combined[combined["automl_tool"] == automl_tool]
        if combined.empty:
            logging.warning(f"[Retrain] No rows for automl_tool={automl_tool}")
            return ""
        suffix += f"_{automl_tool}"

    # Filter to the requested phase to prevent cross-phase feature contamination.
    # Phase 5 ("phase5") rows have rolling features; Phase 1 ("framework") rows do not.
    # Mixing them would create a training set with inconsistent feature presence.
    if phase_tag and "phase" in combined.columns:
        combined = combined[combined["phase"] == phase_tag]
        if combined.empty:
            logging.warning(f"[Retrain] No rows for phase={phase_tag}")
            return ""
        suffix += f"_{phase_tag}"

    # Filter to the requested seed to prevent cross-seed contamination.
    # When multiple seeds of the same simulation mode run in the same directory
    # (e.g. realistic seed=42, seed=123, seed=777 for robustness testing),
    # each seed's training set must remain isolated so results are independent.
    if seed is not None and "simulation_seed" in combined.columns:
        combined = combined[combined["simulation_seed"] == seed]
        if combined.empty:
            logging.warning(f"[Retrain] No rows for simulation_seed={seed}")
            return ""
        suffix += f"_s{seed}"

    output_path = os.path.join(base_dir, f"aggregated_history{suffix}.csv")
    combined.to_csv(output_path, index=False)

    logging.info(
        f"[Retrain] Aggregated {len(history_files)} history files "
        f"({len(combined)} rows, mode={simulation_mode or 'all'}, "
        f"framework={automl_tool or 'all'}, seed={seed if seed is not None else 'all'}) "
        f"-> {output_path}"
    )
    return output_path
