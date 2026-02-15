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

# Common IoT-relevant ports for feature derivation
_COMMON_PORTS = {21, 22, 23, 53, 80, 443, 502, 554, 1883, 5683}


def load_history(path):
    df = pd.read_csv(path)

    df[TARGET] = (
        pd.to_numeric(df[TARGET], errors="coerce")
        .fillna(0)
        .astype(int)
    )

    # Phase 3C: Derive aggregate features from existing columns (no schema change)
    if "container_id" in df.columns and "open_port" in df.columns:
        df["port_count"] = df.groupby("container_id")["open_port"].transform("nunique")
    if "container_id" in df.columns and "protocol" in df.columns:
        df["protocol_diversity"] = df.groupby("container_id")["protocol"].transform("nunique")
    if "open_port" in df.columns:
        df["open_port"] = pd.to_numeric(df["open_port"], errors="coerce").fillna(0).astype(int)
        df["is_common_port"] = df["open_port"].isin(_COMMON_PORTS).astype(int)

    df = df.drop(columns=[c for c in DROP_COLS if c in df.columns])

    return df
