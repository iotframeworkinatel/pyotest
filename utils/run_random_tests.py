"""
Random baseline strategy: selects adaptive tests randomly (no model guidance).

Fair comparison design: random selects the SAME NUMBER of adaptive tests
as AutoML, but chosen at random instead of by model prediction.
This proves the model's intelligence matters, not just having more tests.
"""
import logging
import random
import time

from history.history_builder import HistoryBuilder
from utils.metrics import save_metrics
from utils.protocols import guess_protocol
from utils.run_and_log import run_and_log
from utils.protocol_test_map import PROTOCOL_TESTS
from utils.adaptive_test_map import ADAPTIVE_TESTS


def run_random_tests(iot_devices, experiment, args, n_adaptive=None, seed=None):
    """
    Run ALL static tests (PROTOCOL_TESTS) + a RANDOM subset of adaptive tests.

    Fair comparison: n_adaptive should match the number AutoML selected,
    so both strategies have the SAME test budget. The only difference
    is HOW they pick — model intelligence vs random chance.

    Parameters
    ----------
    n_adaptive : int or None
        How many adaptive tests to randomly select. Should match AutoML's
        adaptive test count for a fair comparison. If None, selects ALL
        adaptive tests (not recommended — unfair comparison).
    seed : int or None
        Random seed for reproducibility within a single experiment.
        Each experiment gets a different seed for variation across runs.
    """
    start = time.time()

    metrics = {
        "tests_executed": 0,
        "vulns_detected": 0,
    }

    history = HistoryBuilder(
        path=experiment.path("history.csv")
    )

    # Seed for this experiment (reproducible within run, different across runs)
    if seed is None:
        seed = int(time.time() * 1000) % (2**31)
    rng = random.Random(seed)

    logging.info(f"[Random] Starting random baseline tests (seed={seed})...")

    # ── 1. Collect all possible adaptive tests per device/port ──
    adaptive_candidates = []
    for d in iot_devices:
        for port in d.ports:
            protocol = guess_protocol(port)
            if protocol in ADAPTIVE_TESTS:
                for test_func, test_id, test_type, auth_required in ADAPTIVE_TESTS[protocol]:
                    adaptive_candidates.append({
                        "device": d,
                        "port": port,
                        "protocol": protocol,
                        "test_func": test_func,
                        "test_id": test_id,
                        "test_type": test_type,
                        "auth_required": auth_required,
                    })

    # ── 2. Randomly select adaptive tests (same budget as AutoML) ──
    if n_adaptive is not None and n_adaptive < len(adaptive_candidates):
        selected_adaptive = rng.sample(adaptive_candidates, n_adaptive)
        logging.info(
            f"[Random] Fair comparison: selecting {n_adaptive}/{len(adaptive_candidates)} "
            f"adaptive tests randomly (matching AutoML budget)"
        )
    elif n_adaptive is not None and n_adaptive >= len(adaptive_candidates):
        # AutoML selected all — random also gets all
        selected_adaptive = list(adaptive_candidates)
        rng.shuffle(selected_adaptive)
        logging.info(
            f"[Random] AutoML selected all {len(adaptive_candidates)} adaptive tests, "
            f"random also runs all"
        )
    else:
        # Fallback: select all (no budget constraint)
        selected_adaptive = list(adaptive_candidates)
        rng.shuffle(selected_adaptive)
        logging.warning(
            f"[Random] No budget constraint — running ALL {len(adaptive_candidates)} "
            f"adaptive tests. Consider passing n_adaptive for fair comparison."
        )

    n_static_total = 0
    n_adaptive_total = len(selected_adaptive)

    # ── 3. Run ALL static tests first (same as general_tester baseline) ──
    logging.info("[Random] Phase 1: Running static tests (PROTOCOL_TESTS)...")
    for d in iot_devices:
        for port in d.ports:
            protocol = guess_protocol(port)
            if protocol not in PROTOCOL_TESTS:
                continue

            for test_func, test_id, test_type, auth_required in PROTOCOL_TESTS[protocol]:
                n_static_total += 1
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
                    strategy="random",
                    auth_required=auth_required,
                )

    # ── 4. Run randomly selected adaptive tests ──
    logging.info(
        f"[Random] Phase 2: Running {n_adaptive_total} randomly selected "
        f"adaptive tests (from {len(adaptive_candidates)} available)..."
    )
    for candidate in selected_adaptive:
        run_and_log(
            test_func=candidate["test_func"],
            test_id=candidate["test_id"],
            test_type=candidate["test_type"],
            device=candidate["device"],
            port=candidate["port"],
            protocol=candidate["protocol"],
            history=history,
            metrics=metrics,
            args=args,
            strategy="random",
            auth_required=candidate["auth_required"],
        )

    logging.info(
        f"[Random] Completed: {n_static_total} static + {n_adaptive_total} adaptive = "
        f"{metrics['tests_executed']} total tests, {metrics['vulns_detected']} vulns found"
    )

    save_metrics({
        "mode": "random",
        "devices": len(iot_devices),
        "tests_executed": metrics["tests_executed"],
        "vulns_detected": metrics["vulns_detected"],
        "adaptive_pool_size": len(adaptive_candidates),
        "adaptive_selected": n_adaptive_total,
        "random_seed": seed,
        "exec_time_sec": int((time.time() - start) * 1000),
    }, path=experiment.path("metrics_random.json"))

    return iot_devices
