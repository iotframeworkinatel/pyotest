import time
from history.history_builder import HistoryBuilder
from utils.metrics import save_metrics
from utils.run_and_log import run_and_log
from utils.protocol_test_map import PROTOCOL_TESTS


def run_adaptive_tests(adaptive_tests_df, iot_devices, experiment, args):

    start = time.time()

    metrics = {
        "tests_executed": 0,
        "vulns_detected": 0
    }

    history = HistoryBuilder(
        path=experiment.path("history.csv")
    )

    for _, row in adaptive_tests_df.iterrows():

        port = int(row["open_port"])
        protocol = row["protocol"]

        if protocol not in PROTOCOL_TESTS:
            continue

        for d in iot_devices:
            if port not in d.ports:
                continue

            for test_func, test_id, _, auth_required in PROTOCOL_TESTS[protocol]:
                run_and_log(
                    test_func=test_func,
                    test_id=test_id,
                    test_type="adaptive",
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
