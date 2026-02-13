# automl/adaptive_generator.py
import logging
import pandas as pd
import h2o
from utils.protocol_test_map import PROTOCOL_TESTS
from utils.adaptive_test_map import ADAPTIVE_TESTS

# ── Default threshold ──────────────────────────────────────────────
# Adaptive-only tests with risk_score >= THRESHOLD are selected.
# Tests from PROTOCOL_TESTS (source="static") are ALWAYS kept.
DEFAULT_RISK_THRESHOLD = 0.3


def _is_valid_test(protocol, test_id):
    """Check if test_id exists in either PROTOCOL_TESTS or ADAPTIVE_TESTS."""
    if protocol in PROTOCOL_TESTS:
        if any(test_id == tid for _, tid, _, _ in PROTOCOL_TESTS[protocol]):
            return True
    if protocol in ADAPTIVE_TESTS:
        if any(test_id == tid for _, tid, _, _ in ADAPTIVE_TESTS[protocol]):
            return True
    return False


def rank_tests(candidates, model, threshold=DEFAULT_RISK_THRESHOLD):
    """
    Rank ALL candidates by predicted vulnerability risk, then apply
    dynamic filtering:

      - source="static"   → ALWAYS included (baseline consistency)
      - source="adaptive"  → included ONLY if risk_score >= threshold
                              (model dynamically selects these)

    Returns a DataFrame with columns:
        ...original columns..., risk_score, selected (bool)
    """
    # ── 1. Score ALL candidates with the trained model ──
    # We need to drop 'source' before feeding to H2O (not a training feature)
    score_cols = [c for c in candidates.columns if c not in ("source", "test_id")]
    hf = h2o.H2OFrame(candidates[score_cols])
    preds = model.predict(hf).as_data_frame()

    if "p1" not in preds.columns:
        preds["p1"] = 0.0

    candidates = candidates.copy()
    risk_scores = preds["p1"].fillna(0.0).values  # .values avoids index mismatch
    candidates["risk_score"] = risk_scores.astype(float)

    # ── 2. Validate test_ids ──
    valid_mask = candidates.apply(
        lambda row: _is_valid_test(row["protocol"], row["test_id"]),
        axis=1
    )
    df = candidates[valid_mask].copy()

    # ── 3. Dynamic selection ──
    # Static tests: always selected (they replicate the general_tester baseline)
    # Adaptive tests: selected only when model predicts risk_score >= threshold
    df["selected"] = df.apply(
        lambda row: True if row["source"] == "static"
        else row["risk_score"] >= threshold,
        axis=1
    )

    # ── 4. Sort by risk_score (highest first) ──
    df = df.sort_values("risk_score", ascending=False).reset_index(drop=True)

    # ── 5. Log selection summary ──
    total_adaptive = (df["source"] == "adaptive").sum()
    selected_adaptive = ((df["source"] == "adaptive") & df["selected"]).sum()
    skipped_adaptive = total_adaptive - selected_adaptive
    total_static = (df["source"] == "static").sum()

    logging.info(
        f"[AutoML] Test selection (threshold={threshold:.2f}): "
        f"{total_static} static (always) + "
        f"{selected_adaptive}/{total_adaptive} adaptive selected "
        f"({skipped_adaptive} filtered out by model)"
    )

    # Log per-protocol breakdown
    for protocol in sorted(df["protocol"].unique()):
        proto_df = df[df["protocol"] == protocol]
        proto_adaptive = proto_df[proto_df["source"] == "adaptive"]
        proto_selected = proto_adaptive[proto_adaptive["selected"]]
        proto_static = proto_df[proto_df["source"] == "static"]

        if len(proto_adaptive) > 0:
            logging.info(
                f"  [{protocol}] static={len(proto_static)}, "
                f"adaptive={len(proto_selected)}/{len(proto_adaptive)} "
                f"(scores: {proto_adaptive['risk_score'].min():.3f}–{proto_adaptive['risk_score'].max():.3f})"
            )

    return df
