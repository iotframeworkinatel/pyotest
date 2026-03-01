"""
ML Risk Scorer — uses trained H2O model to score test cases by vulnerability likelihood.
"""
import logging
from typing import Optional

import pandas as pd

from models.test_case import TestSuite
from utils.protocols import PORT_PROTOCOL_MAP

# Common IoT-relevant ports for feature derivation
_COMMON_PORTS = {21, 22, 23, 53, 80, 443, 502, 554, 1883, 5683}


def score_test_suite(suite: TestSuite) -> TestSuite:
    """
    Score each test case in the suite using the trained H2O model.
    If no model is available, returns suite unscored.

    Adds risk_score (0.0-1.0) and is_recommended flag to each TestCase.
    Sorts test cases by risk_score descending.
    """
    from automl.pipeline import get_model

    model = get_model()
    if model is None:
        logging.info("[Scorer] No trained model available — returning unscored suite")
        return suite

    try:
        import h2o

        # Build feature DataFrame matching training schema
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
            return suite

        df = pd.DataFrame(rows)

        # Convert categoricals to match training schema
        for col in ["test_strategy", "device_type", "firmware_version", "protocol", "service"]:
            if col in df.columns:
                df[col] = df[col].astype(str)

        hf = h2o.H2OFrame(df)
        preds = model.predict(hf)
        pred_df = preds.as_data_frame()

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
            f"[Scorer] Scored {scored_count} tests, {recommended} recommended (risk >= 0.5)"
        )

    except Exception as e:
        logging.warning(f"[Scorer] Failed to score tests: {e}")

    return suite


def _get_device_ports(suite: TestSuite, ip: str) -> list[int]:
    """Get all ports for a device from the suite's device list."""
    for dev in suite.devices:
        if dev.get("ip") == ip:
            return [int(p) for p in dev.get("ports", [])]
    return []
