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


def score_test_suite(suite: TestSuite, automl_tool: str = "h2o") -> TestSuite:
    """
    Score each test case in the suite using the trained AutoML model.
    If no model is available, returns suite unscored.

    Args:
        suite: TestSuite to score.
        automl_tool: Framework name (h2o, autogluon, pycaret, tpot, autosklearn).

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
        df = _build_feature_dataframe(suite)
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


def _build_feature_dataframe(suite: TestSuite) -> Optional[pd.DataFrame]:
    """Build the feature DataFrame from a TestSuite for model prediction.

    Extracts features from each test case that match the training schema:
    test_strategy, device_type, firmware_version, open_port, protocol,
    service, auth_required, port_count, protocol_diversity, is_common_port.
    """
    rows = []
    for tc in suite.test_cases:
        # Compute device-level features
        device_ports = _get_device_ports(suite, tc.target_ip)
        device_protocols = set(
            PORT_PROTOCOL_MAP.get(p, "generic") for p in device_ports
        )

        rows.append({
            "test_strategy": "generated",
            "device_type": "unknown",
            "firmware_version": "unknown",
            "open_port": tc.port,
            "protocol": tc.protocol,
            "service": tc.protocol,
            "auth_required": tc.auth_required,
            "port_count": len(device_ports),
            "protocol_diversity": len(device_protocols),
            "is_common_port": 1 if tc.port in _COMMON_PORTS else 0,
        })

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
