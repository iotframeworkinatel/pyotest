from automl.dataset import load_history
from automl.train import train_automl
from automl.candidates import generate_candidates
from automl.adaptive_generator import rank_tests
import pandas as pd

def run_automl(iot_devices, experiment):
    history = load_history(
        path=experiment.path("history.csv")
    )

    aml = train_automl(history)

    candidates = pd.DataFrame(
        generate_candidates(iot_devices)
    )

    best_tests = rank_tests(candidates, aml.leader)

    best_tests = best_tests.drop_duplicates(
        subset=["open_port", "protocol"]
    )

    best_tests.to_csv(
        experiment.path("automl_tests.csv"),
        index=False
    )

    return best_tests
