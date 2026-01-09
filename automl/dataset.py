import pandas as pd

TARGET = "vulnerability_found"

DROP_COLS = [
    "experiment_id",
    "timestamp",
    "container_id",
    "test_id",
    "test_type",
    "execution_time_ms"
]

def load_history(path):
    df = pd.read_csv(path)

    df[TARGET] = (
        pd.to_numeric(df[TARGET], errors="coerce")
        .fillna(0)
        .astype(int)
    )

    df = df.drop(columns=[c for c in DROP_COLS if c in df.columns])

    return df
