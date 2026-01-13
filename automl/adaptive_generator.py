# automl/rank_tests.py
import pandas as pd
import h2o
from utils.protocol_test_map import PROTOCOL_TESTS

def rank_tests(candidates, model):
    """Rank tests by predicted vulnerability risk using trained AutoML model."""
    hf = h2o.H2OFrame(candidates)
    preds = model.predict(hf).as_data_frame()

    # Handle missing or invalid prediction columns
    if "p1" not in preds.columns:
        preds["p1"] = 0.0

    candidates["risk_score"] = preds.get("p1", 0).fillna(0.0)

    # Filter only valid (protocol, test_id) pairs
    valid = []
    for _, row in candidates.iterrows():
        protocol = row["protocol"]
        test_id = row["test_id"]
        if protocol in PROTOCOL_TESTS and any(test_id == tid for _, tid, _, _ in PROTOCOL_TESTS[protocol]):
            valid.append(row)

    df = pd.DataFrame(valid).sort_values("risk_score", ascending=False)
    df["risk_score"] = df["risk_score"].astype(float).fillna(0.0)
    return df
