import logging
import time
from history.history_builder import HistoryBuilder
from utils.metrics import save_metrics
from utils.protocols import PORT_PROTOCOL_MAP
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

    logging.info("Starting adaptive vulnerability tests...")

    # 🚫 Remove duplicados (garantia)
    adaptive_tests_df = adaptive_tests_df.drop_duplicates(
        subset=["open_port", "protocol", "test_id"]
    )

    for _, row in adaptive_tests_df.iterrows():
        port = int(row["open_port"])
        protocol = row["protocol"]
        test_id = row.get("test_id")

        if protocol not in PROTOCOL_TESTS:
            continue

        for d in iot_devices:
            # executa somente nos dispositivos com a porta em questão
            if port not in d.ports:
                continue

            for test_func, defined_test_id, test_type, auth_required in PROTOCOL_TESTS[protocol]:
                # 👇 executa só o teste sugerido pelo modelo
                if test_id and defined_test_id != test_id:
                    continue

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
