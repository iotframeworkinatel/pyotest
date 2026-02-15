import logging
import pandas as pd

from utils.protocol_test_map import PROTOCOL_TESTS
from utils.adaptive_test_map import ADAPTIVE_TESTS
from utils.protocols import guess_protocol

# Common IoT-relevant ports (matching dataset.py)
_COMMON_PORTS = {21, 22, 23, 53, 80, 443, 502, 554, 1883, 5683}


def _build_candidate_row(device, port, protocol, test_id, auth_required, source,
                          port_count=1, protocol_diversity=1):
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
        # Phase 3C: Derived features (matching dataset.py load_history)
        "port_count": port_count,
        "protocol_diversity": protocol_diversity,
        "is_common_port": 1 if port in _COMMON_PORTS else 0,
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

    # Phase 3C: Pre-compute per-device aggregate features
    device_features = {}
    for d in iot_devices:
        key = getattr(d, "ip", id(d))
        port_count = len(d.ports) if d.ports else 1
        protocols = set(guess_protocol(p) for p in (d.ports or []))
        protocol_diversity = len(protocols) if protocols else 1
        device_features[key] = (port_count, protocol_diversity)

    for d in iot_devices:
        key = getattr(d, "ip", id(d))
        pc, pd_val = device_features.get(key, (1, 1))

        for port in d.ports:
            protocol = guess_protocol(port)

            # Static tests — always re-executed in automl mode
            if protocol in PROTOCOL_TESTS:
                for _, test_id, _, auth_required in PROTOCOL_TESTS[protocol]:
                    rows.append(_build_candidate_row(
                        d, port, protocol, test_id, auth_required, source="static",
                        port_count=pc, protocol_diversity=pd_val,
                    ))

            # Adaptive-only tests — subject to model filtering
            if protocol in ADAPTIVE_TESTS:
                for _, test_id, _, auth_required in ADAPTIVE_TESTS[protocol]:
                    rows.append(_build_candidate_row(
                        d, port, protocol, test_id, auth_required, source="adaptive",
                        port_count=pc, protocol_diversity=pd_val,
                    ))

    df = pd.DataFrame(rows).drop_duplicates(
        subset=["open_port", "protocol", "test_id"]
    )

    n_static = (df["source"] == "static").sum()
    n_adaptive = (df["source"] == "adaptive").sum()
    logging.info(f"[AutoML] Candidates generated: {n_static} static + {n_adaptive} adaptive = {len(df)} total")

    return df
