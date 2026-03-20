import pandas as pd

TARGET = "vulnerability_found"

DROP_COLS = [
    # Infrastructure / identity — not predictive
    "experiment_id",
    "timestamp",
    "container_id",
    "test_id",
    "test_type",
    "execution_time_ms",
    "simulation_mode",
    "simulation_iteration",
    # Experiment metadata — unavailable at scoring time
    # (scorer.py builds features from a live TestSuite, not from history rows)
    "automl_tool",
    "baseline_strategy",
    "exp_dir_name",
    "payload_size",
    "timeout",
    "phase",
    "score_method",
    "test_origin",
]

# Common IoT-relevant ports for feature derivation
_COMMON_PORTS = {21, 22, 23, 53, 80, 443, 502, 554, 1883, 5683}

# Rolling window sizes — shared with scorer.py for symmetric train/score features
_ROLLING_PROTO_WINDOW = 10  # iterations for protocol-level rolling mean
_ROLLING_TYPE_WINDOW = 5    # iterations for (protocol, test_type) rolling mean


def compute_rolling_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add rolling temporal features to a history DataFrame.

    Uses iteration-level aggregation before rolling to avoid within-iteration
    leakage (each iteration produces ~14 rows from 14 containers — naive row-level
    rolling would let rows within the same iteration see each other).

    Strategy:
      1. Collapse to one mean per (protocol, simulation_iteration).
      2. Sort by iteration, shift by 1 so iteration k never sees its own outcome.
      3. Roll over _ROLLING_PROTO_WINDOW / _ROLLING_TYPE_WINDOW iterations.
      4. Merge back to the full row-level DataFrame.

    Adds columns:
      - recent_vuln_rate:    rolling mean detection rate for this protocol
      - test_type_vuln_rate: rolling mean detection rate for (protocol, test_type)

    Requires columns: protocol, simulation_iteration, vulnerability_found.
    Returns a new DataFrame with the two columns added (0.0 where no history).
    """
    df = df.copy()

    if "simulation_iteration" not in df.columns or "protocol" not in df.columns:
        df["recent_vuln_rate"] = 0.0
        df["test_type_vuln_rate"] = 0.0
        return df

    # ── recent_vuln_rate: protocol-level, 10-iter window, shifted ──
    proto_iter = (
        df.groupby(["protocol", "simulation_iteration"])["vulnerability_found"]
        .mean()
        .reset_index()
        .rename(columns={"vulnerability_found": "_pm"})
        .sort_values(["protocol", "simulation_iteration"])
    )
    proto_iter["recent_vuln_rate"] = (
        proto_iter.groupby("protocol")["_pm"]
        .transform(
            lambda s: s.shift(1).rolling(_ROLLING_PROTO_WINDOW, min_periods=1).mean()
        )
        .fillna(0.0)
    )
    df = df.merge(
        proto_iter[["protocol", "simulation_iteration", "recent_vuln_rate"]],
        on=["protocol", "simulation_iteration"],
        how="left",
    )

    # ── test_type_vuln_rate: (protocol, test_type)-level, 5-iter window ──
    if "test_type" in df.columns:
        pt_iter = (
            df.groupby(["protocol", "test_type", "simulation_iteration"])[
                "vulnerability_found"
            ]
            .mean()
            .reset_index()
            .rename(columns={"vulnerability_found": "_ptm"})
            .sort_values(["protocol", "test_type", "simulation_iteration"])
        )
        pt_iter["test_type_vuln_rate"] = (
            pt_iter.groupby(["protocol", "test_type"])["_ptm"]
            .transform(
                lambda s: s.shift(1).rolling(_ROLLING_TYPE_WINDOW, min_periods=1).mean()
            )
            .fillna(0.0)
        )
        df = df.merge(
            pt_iter[
                ["protocol", "test_type", "simulation_iteration", "test_type_vuln_rate"]
            ],
            on=["protocol", "test_type", "simulation_iteration"],
            how="left",
        )
    else:
        df["test_type_vuln_rate"] = 0.0

    df[["recent_vuln_rate", "test_type_vuln_rate"]] = df[
        ["recent_vuln_rate", "test_type_vuln_rate"]
    ].fillna(0.0)
    return df


def load_history(path: str, dynamic: bool = False) -> pd.DataFrame:
    """Load and feature-engineer a history CSV for AutoML training.

    Args:
        path:    Path to history CSV (individual experiment or aggregated).
        dynamic: If True, compute rolling temporal features (Phase 5/6).
                 If False (default), static feature set only (Phase 1/2/3).

    Returns:
        DataFrame ready for adapter.train().
    """
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
        df["protocol_diversity"] = df.groupby("container_id")["protocol"].transform(
            "nunique"
        )
    if "open_port" in df.columns:
        df["open_port"] = (
            pd.to_numeric(df["open_port"], errors="coerce").fillna(0).astype(int)
        )
        df["is_common_port"] = df["open_port"].isin(_COMMON_PORTS).astype(int)

    # Phase 5/6: Rolling temporal features — give the model a signal that evolves
    if dynamic:
        df = compute_rolling_features(df)
        # Keep simulation_iteration as a temporal feature; drop everything else as usual
        _drop = [c for c in DROP_COLS if c != "simulation_iteration"]
    else:
        _drop = DROP_COLS

    df = df.drop(columns=[c for c in _drop if c in df.columns])

    return df
