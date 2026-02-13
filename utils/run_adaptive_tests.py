import logging
import time
from history.history_builder import HistoryBuilder
from utils.metrics import save_metrics
from utils.protocols import PORT_PROTOCOL_MAP
from utils.run_and_log import run_and_log
from utils.protocol_test_map import PROTOCOL_TESTS
from utils.adaptive_test_map import ADAPTIVE_TESTS


def _resolve_test(protocol, test_id):
    """
    Resolve a test_id to its (test_func, test_id, test_type, auth_required)
    from either PROTOCOL_TESTS or ADAPTIVE_TESTS.
    Returns None if not found.
    """
    if protocol in PROTOCOL_TESTS:
        for test_func, tid, test_type, auth_required in PROTOCOL_TESTS[protocol]:
            if tid == test_id:
                return test_func, tid, test_type, auth_required

    if protocol in ADAPTIVE_TESTS:
        for test_func, tid, test_type, auth_required in ADAPTIVE_TESTS[protocol]:
            if tid == test_id:
                return test_func, tid, test_type, auth_required

    return None


def run_adaptive_tests(adaptive_tests_df, iot_devices, experiment, args):
    start = time.time()

    metrics = {
        "tests_executed": 0,
        "vulns_detected": 0
    }

    history = HistoryBuilder(
        path=experiment.path("history.csv")
    )

    logging.info("Starting adaptive vulnerability tests...")

    # Remove duplicados (garantia)
    adaptive_tests_df = adaptive_tests_df.drop_duplicates(
        subset=["open_port", "protocol", "test_id"]
    )

    # ── Log execution plan ──
    n_static = (adaptive_tests_df["source"] == "static").sum() if "source" in adaptive_tests_df.columns else "?"
    n_adaptive = (adaptive_tests_df["source"] == "adaptive").sum() if "source" in adaptive_tests_df.columns else "?"
    logging.info(
        f"[AutoML] Executing {len(adaptive_tests_df)} selected tests "
        f"({n_static} static + {n_adaptive} adaptive)"
    )

    for _, row in adaptive_tests_df.iterrows():
        port = int(row["open_port"])
        protocol = row["protocol"]
        test_id = row.get("test_id")
        source = row.get("source", "unknown")
        risk_score = row.get("risk_score", 0.0)

        # Resolve test function from either dict
        resolved = _resolve_test(protocol, test_id)
        if resolved is None:
            continue

        test_func, defined_test_id, test_type, auth_required = resolved

        for d in iot_devices:
            # executa somente nos dispositivos com a porta em questão
            if port not in d.ports:
                continue

            logging.debug(
                f"  → [{source}] {defined_test_id} on {d.ip}:{port} "
                f"(risk_score={risk_score:.3f})"
            )

            run_and_log(
                test_func=test_func,
                test_id=defined_test_id,
                test_type=test_type,
                device=d,
                port=port,
                protocol=protocol,
                history=history,
                metrics=metrics,
                args=args,
                strategy="automl",
                auth_required=auth_required
            )

    save_metrics({
        "mode": "automl",
        "devices": len(iot_devices),
        "tests_executed": metrics["tests_executed"],
        "vulns_detected": metrics["vulns_detected"],
        "exec_time_sec": int((time.time() - start) * 1000)
    }, path=experiment.path("metrics_automl.json"))

    return iot_devices
