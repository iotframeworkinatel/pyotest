"""
ML Risk Scorer — uses a trained AutoML model to score test cases by vulnerability likelihood.

Supports multiple AutoML frameworks via the adapter pattern. Defaults to H2O
for backward compatibility.
"""
import logging
from typing import Optional

import pandas as pd

from models.test_case import TestSuite
from utils.protocols import PORT_PROTOCOL_MAP

# Common IoT-relevant ports for feature derivation
_COMMON_PORTS = {21, 22, 23, 53, 80, 443, 502, 554, 1883, 5683}


def score_test_suite(
    suite: TestSuite,
    automl_tool: str = "h2o",
    history_df: Optional[pd.DataFrame] = None,
    current_iter: int = 0,
) -> TestSuite:
    """
    Score each test case in the suite using the trained AutoML model.
    If no model is available, returns suite unscored.

    Args:
        suite:        TestSuite to score.
        automl_tool:  Framework name (h2o, autogluon, pycaret, tpot, autosklearn).
        history_df:   Aggregated history DataFrame for Phase 5/6 dynamic features.
                      When provided, rolling protocol/test-type detection rates are
                      computed and added as scoring features to mirror training.
                      When None (default), static features only — Phase 1/2/3
                      behaviour is completely unchanged.
        current_iter: Current simulation iteration. History is filtered to
                      iterations < current_iter to prevent future leakage.

    Adds risk_score (0.0-1.0) and is_recommended flag to each TestCase.
    Sorts test cases by risk_score descending.
    """
    from automl.pipeline import get_adapter_for_scoring

    adapter = get_adapter_for_scoring(automl_tool)
    if adapter is None:
        logging.info(
            f"[Scorer] No trained {automl_tool} model available — clearing scores"
        )
        # Clear any stale scores from a previously-used framework so they
        # don't leak through when the user switches AutoML tools.
        for tc in suite.test_cases:
            tc.risk_score = None
            tc.is_recommended = False
        return suite

    try:
        # Build feature DataFrame matching training schema
        df = _build_feature_dataframe(suite, history_df=history_df,
                                       current_iter=current_iter)
        if df is None or df.empty:
            return suite

        # Use adapter.predict() — returns DataFrame with p1 column
        pred_df = adapter.predict(df)

        # Extract p1 (probability of vulnerability_found=1)
        if "p1" in pred_df.columns:
            scores = pred_df["p1"].tolist()
        elif len(pred_df.columns) >= 3:
            scores = pred_df.iloc[:, 2].tolist()
        else:
            scores = pred_df.iloc[:, 0].tolist()

        # Apply scores to test cases
        for tc, score in zip(suite.test_cases, scores):
            tc.risk_score = round(float(score), 4)
            tc.is_recommended = tc.risk_score >= 0.5

        # Sort by risk score (highest first)
        suite.test_cases.sort(key=lambda tc: tc.risk_score or 0.0, reverse=True)

        scored_count = sum(1 for tc in suite.test_cases if tc.risk_score is not None)
        recommended = sum(1 for tc in suite.test_cases if tc.is_recommended)
        logging.info(
            f"[Scorer:{automl_tool}] Scored {scored_count} tests, "
            f"{recommended} recommended (risk >= 0.5)"
        )

    except Exception as e:
        logging.warning(f"[Scorer:{automl_tool}] Failed to score tests: {e}")

    return suite


def _build_feature_dataframe(
    suite: TestSuite,
    history_df: Optional[pd.DataFrame] = None,
    current_iter: int = 0,
) -> Optional[pd.DataFrame]:
    """Build the feature DataFrame from a TestSuite for model prediction.

    Phase 1/2/3 (history_df=None): static features only —
      test_strategy, device_type, firmware_version, open_port, protocol,
      service, auth_required, port_count, protocol_diversity, is_common_port.

    Phase 5/6 (history_df provided): also adds rolling temporal features
      that mirror compute_rolling_features() in dataset.py —
      recent_vuln_rate, test_type_vuln_rate, simulation_iteration.
    """
    # ── Pre-compute rolling priors from history (Phase 5/6 only) ──────────
    _proto_rates: dict = {}
    _pt_rates: dict = {}

    if history_df is not None and not history_df.empty and current_iter > 1:
        try:
            from automl.dataset import _ROLLING_PROTO_WINDOW, _ROLLING_TYPE_WINDOW

            _h = history_df.copy()
            if "vulnerability_found" in _h.columns:
                _h["vulnerability_found"] = pd.to_numeric(
                    _h["vulnerability_found"], errors="coerce"
                ).fillna(0)

            # Only use history strictly before current iteration
            if "simulation_iteration" in _h.columns:
                _h = _h[_h["simulation_iteration"] < current_iter]

            if not _h.empty and "protocol" in _h.columns:
                # Protocol-level: mean over last _ROLLING_PROTO_WINDOW iterations
                if "simulation_iteration" in _h.columns:
                    _recent = sorted(_h["simulation_iteration"].unique())[
                        -_ROLLING_PROTO_WINDOW:
                    ]
                    _w = _h[_h["simulation_iteration"].isin(_recent)]
                else:
                    _w = _h
                _proto_rates = (
                    _w.groupby("protocol")["vulnerability_found"].mean().to_dict()
                )

                # (protocol, test_type)-level: last _ROLLING_TYPE_WINDOW iterations
                if "test_type" in _h.columns:
                    if "simulation_iteration" in _h.columns:
                        _trecent = sorted(_h["simulation_iteration"].unique())[
                            -_ROLLING_TYPE_WINDOW:
                        ]
                        _tw = _h[_h["simulation_iteration"].isin(_trecent)]
                    else:
                        _tw = _h
                    _pt_rates = {
                        k: float(v)
                        for k, v in _tw.groupby(["protocol", "test_type"])[
                            "vulnerability_found"
                        ]
                        .mean()
                        .items()
                    }
        except Exception as e:
            logging.warning(f"[Scorer] Failed to compute rolling priors: {e}")

    # ── Build per-test-case feature rows ──────────────────────────────────
    rows = []
    for tc in suite.test_cases:
        # Compute device-level features
        device_ports = _get_device_ports(suite, tc.target_ip)
        device_protocols = set(
            PORT_PROTOCOL_MAP.get(p, "generic") for p in device_ports
        )

        _origin = getattr(tc, "test_origin", "registry")
        row = {
            "test_strategy": "llm_generated" if _origin == "llm" else "generated",
            "device_type": "unknown",
            "firmware_version": "unknown",
            "open_port": tc.port,
            "protocol": tc.protocol,
            "service": tc.protocol,
            "auth_required": tc.auth_required,
            "port_count": len(device_ports),
            "protocol_diversity": len(device_protocols),
            "is_common_port": 1 if tc.port in _COMMON_PORTS else 0,
        }

        # Dynamic features — only added when history context is provided (Phase 5/6).
        # Mirrors the rolling feature computation in dataset.compute_rolling_features().
        if history_df is not None:
            row["simulation_iteration"] = current_iter
            row["recent_vuln_rate"] = _proto_rates.get(tc.protocol, 0.0)
            # vulnerability_type is the closest attribute to test_type on TestCase
            _vtype = getattr(tc, "vulnerability_type", "")
            row["test_type_vuln_rate"] = _pt_rates.get((tc.protocol, _vtype), 0.0)

        rows.append(row)

    if not rows:
        return None

    df = pd.DataFrame(rows)

    # Convert categoricals to match training schema
    for col in ["test_strategy", "device_type", "firmware_version", "protocol", "service"]:
        if col in df.columns:
            df[col] = df[col].astype(str)

    return df


def _get_device_ports(suite: TestSuite, ip: str) -> list[int]:
    """Get all ports for a device from the suite's device list."""
    for dev in suite.devices:
        if dev.get("ip") == ip:
            return [int(p) for p in dev.get("ports", [])]
    return []
