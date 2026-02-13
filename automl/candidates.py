import logging
import pandas as pd

from utils.protocol_test_map import PROTOCOL_TESTS
from utils.adaptive_test_map import ADAPTIVE_TESTS
from utils.protocols import guess_protocol


def _build_candidate_row(device, port, protocol, test_id, auth_required, source):
    """Build a single candidate row dict."""
    return {
        "test_strategy": "automl",
        "device_type": getattr(device, "device_type", "unknown"),
        "firmware_version": getattr(device, "os", "unknown"),
        "open_port": port,
        "protocol": protocol,
        "service": protocol,
        "test_id": test_id,
        "auth_required": auth_required,
        "source": source,          # "static" or "adaptive"
    }


def generate_candidates(iot_devices):
    """
    Generate ALL candidate tests for scoring by the model.
    Each candidate is tagged with source="static" or source="adaptive"
    so the pipeline can treat them differently after ranking.

    - static  : same tests as general_tester (PROTOCOL_TESTS)
                 → always re-executed (baseline guarantee)
    - adaptive: additional tests (ADAPTIVE_TESTS)
                 → dynamically filtered by model risk_score
    """
    rows = []

    for d in iot_devices:
        for port in d.ports:
            protocol = guess_protocol(port)

            # Static tests — always re-executed in automl mode
            if protocol in PROTOCOL_TESTS:
                for _, test_id, _, auth_required in PROTOCOL_TESTS[protocol]:
                    rows.append(_build_candidate_row(
                        d, port, protocol, test_id, auth_required, source="static"
                    ))

            # Adaptive-only tests — subject to model filtering
            if protocol in ADAPTIVE_TESTS:
                for _, test_id, _, auth_required in ADAPTIVE_TESTS[protocol]:
                    rows.append(_build_candidate_row(
                        d, port, protocol, test_id, auth_required, source="adaptive"
                    ))

    df = pd.DataFrame(rows).drop_duplicates(
        subset=["open_port", "protocol", "test_id"]
    )

    n_static = (df["source"] == "static").sum()
    n_adaptive = (df["source"] == "adaptive").sum()
    logging.info(f"[AutoML] Candidates generated: {n_static} static + {n_adaptive} adaptive = {len(df)} total")

    return df
