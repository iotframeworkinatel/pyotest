import time
import logging
from history.history_builder import HistoryBuilder
from utils.metrics import save_metrics
from utils.run_and_log import run_and_log
from utils.protocol_test_map import PROTOCOL_TESTS
from vulnerability_tester import grab_banner


PORT_PROTOCOL_MAP = {
    21: "ftp",
    22: "ssh",
    23: "telnet",
    80: "http",
    1883: "mqtt",
    554: "rtsp",
}


def general_tester(iot_devices, experiment, args):

    start = time.time()

    metrics = {
        "tests_executed": 0,
        "vulns_detected": 0
    }

    history = HistoryBuilder(
        path=experiment.path("history.csv")
    )

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO
    )

    logging.info("Starting static vulnerability tests...")

    for d in iot_devices:
        for port in d.ports:

            protocol = PORT_PROTOCOL_MAP.get(port)

            if protocol and protocol in PROTOCOL_TESTS:
                for test_func, test_id, test_type, auth_required in PROTOCOL_TESTS[protocol]:
                    run_and_log(
                        test_func=test_func,
                        test_id=test_id,
                        test_type=test_type,
                        device=d,
                        port=port,
                        protocol=protocol,
                        history=history,
                        metrics=metrics,
                        args=args,
                        strategy="static",
                        auth_required=auth_required
                    )

            # # Banner grabbing sempre
            # run_and_log(
            #     test_func=grab_banner,
            #     test_id="banner_grab",
            #     test_type="information_disclosure",
            #     device=d,
            #     port=port,
            #     protocol="generic",
            #     history=history,
            #     metrics=metrics,
            #     strategy="static"
            # )

    save_metrics({
        "mode": "static",
        "devices": len(iot_devices),
        "tests_executed": metrics["tests_executed"],
        "vulns_detected": metrics["vulns_detected"],
        "exec_time_sec": int((time.time() - start) * 1000)
    }, path=experiment.path("metrics_static.json"))

    return iot_devices
