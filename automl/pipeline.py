import json
import logging

from automl.dataset import load_history
from automl.train import train_automl, extract_model_metrics
from automl.candidates import generate_candidates
from automl.adaptive_generator import rank_tests
import pandas as pd

def run_automl(iot_devices, experiment):
    history = load_history(
        path=experiment.path("history.csv")
    )

    aml = train_automl(history)

    # ── Extract and save model performance metrics ──
    try:
        model_metrics = extract_model_metrics(aml)
        with open(experiment.path("model_metrics.json"), "w") as f:
            json.dump(model_metrics, f, indent=2, default=str)
        logging.info(
            f"[AutoML] Model metrics saved — Leader: {model_metrics.get('leader_algo', '?')}, "
            f"AUC: {model_metrics.get('auc', '?')}, "
            f"Models trained: {model_metrics.get('total_models_trained', '?')}"
        )
    except Exception as e:
        logging.warning(f"[AutoML] Could not save model metrics: {e}")

    candidates = generate_candidates(iot_devices)

    # rank_tests now scores ALL candidates and marks each as selected/not
    all_tests = rank_tests(candidates, aml.leader)

    # ── Save FULL ranked list (with risk_score + selected flag) for auditing ──
    all_tests.to_csv(
        experiment.path("automl_tests.csv"),
        index=False
    )

    # ── Return ONLY selected tests to the runner ──
    selected = all_tests[all_tests["selected"] == True].copy()

    n_total = len(all_tests)
    n_selected = len(selected)
    logging.info(
        f"[AutoML] Pipeline: {n_selected}/{n_total} tests selected for execution"
    )

    return selected
