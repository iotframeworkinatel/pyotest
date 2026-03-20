"""
Suite Runner — executes a TestSuite by rendering Jinja2 templates into
executable pytest files and running them against target devices.
Called by the dashboard API inside the scanner container.
"""
import json
import logging
import os
import random
import subprocess
import time
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from models.test_case import TestSuite
from history.history_builder import HistoryBuilder
from experiments.manager import ExperimentManager

TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "..", "templates")


_SIMULATION_CONTEXT_PATH = "/app/simulation/runner_context.json"


def run_suite_from_json(suite_json_path: str, simulation_context: dict = None) -> dict:
    """
    Load a TestSuite from JSON and execute all test cases.
    Returns execution result dict.

    simulation_context: optional dict with keys:
        mode, seed, iteration, false_positive_rate, false_negative_rate.
        If None, auto-reads from /app/simulation/runner_context.json if present.
    """
    # Auto-load simulation context from shared volume if not explicitly passed
    if simulation_context is None:
        try:
            if os.path.exists(_SIMULATION_CONTEXT_PATH):
                with open(_SIMULATION_CONTEXT_PATH) as f:
                    simulation_context = json.load(f)
                logging.info(
                    f"[SuiteRunner] Loaded simulation context: "
                    f"mode={simulation_context.get('mode')}, "
                    f"iter={simulation_context.get('iteration')}"
                )
        except Exception as e:
            logging.warning(f"[SuiteRunner] Could not read simulation context: {e}")

    with open(suite_json_path) as f:
        data = json.load(f)

    suite = TestSuite.from_dict(data)
    return run_suite(suite, simulation_context=simulation_context)


def run_suite(suite: TestSuite, simulation_context: dict = None) -> dict:
    """
    Execute all test cases in a TestSuite by rendering Jinja2 templates
    into pytest files and running them. Results are parsed from pytest
    output and logged to history.csv.

    simulation_context: optional dict for FP/FN noise injection.
    """
    experiment = ExperimentManager()
    history = HistoryBuilder(experiment.path("history.csv"))
    metrics = {"tests_executed": 0, "vulns_detected": 0}

    # Build simulation RNG if active
    _sim_rng = None
    _sim_fp_rate = 0.0
    _sim_fn_rate = 0.0
    _sim_mode = None
    _sim_iteration = None
    _sim_seed = None
    if simulation_context:
        _sim_mode = simulation_context.get("mode")
        _sim_iteration = simulation_context.get("iteration")
        _sim_seed = simulation_context.get("seed")
        _sim_fp_rate = simulation_context.get("false_positive_rate", 0.0)
        _sim_fn_rate = simulation_context.get("false_negative_rate", 0.0)
        seed = simulation_context.get("seed", 42)
        iteration = simulation_context.get("iteration", 1)
        # Deterministic RNG per iteration — different prime from environment.py
        _sim_rng = random.Random(seed + iteration * 6271)

    start_time = time.time()
    results_detail = []

    # Create directory for rendered test files
    tests_dir = Path(experiment.root) / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)

    # Group test cases by (protocol, target_ip), separating LLM tests
    groups = {}
    llm_tests = []
    for tc in suite.test_cases:
        if getattr(tc, 'test_origin', 'registry') == 'llm' and getattr(tc, 'pytest_code', None):
            llm_tests.append(tc)
        else:
            key = (tc.protocol, tc.target_ip)
            groups.setdefault(key, []).append(tc)

    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))

    # ── Execute registry tests (Jinja2 template-based) ──
    for (protocol, target_ip), test_cases in groups.items():
        # Collect ports for this device/protocol
        ports = sorted(set(str(tc.port) for tc in test_cases))
        ip_safe = target_ip.replace(".", "_")
        filename = f"test_{protocol}_{ip_safe}.py"
        filepath = tests_dir / filename

        # Try to render protocol-specific template
        template_name = f"{protocol}_test.py.j2"
        rendered = None
        try:
            template = env.get_template(template_name)
            rendered = template.render(
                ip=target_ip,
                ports=",".join(ports),
                test_cases=test_cases,
                suite_name=suite.name,
                suite_id=suite.suite_id,
            )
        except Exception:
            # Try generic template as fallback
            try:
                template = env.get_template("generic_test.py.j2")
                rendered = template.render(
                    ip=target_ip,
                    ports=",".join(ports),
                    test_cases=test_cases,
                    protocol=protocol,
                )
            except Exception as e:
                logging.warning(
                    f"[SuiteRunner] No template for {protocol}: {e}"
                )

        if rendered is None:
            # No template available — skip these test cases
            for tc in test_cases:
                results_detail.append(_build_result_entry(
                    tc, status="skipped",
                    reason=f"No template for protocol {protocol}",
                ))
            continue

        # Write rendered test file
        filepath.write_text(rendered, encoding="utf-8")

        # Execute via pytest
        try:
            proc = subprocess.run(
                ["pytest", filename, "-v", "--tb=short", "--no-header"],
                capture_output=True,
                text=True,
                timeout=120,
                cwd=str(tests_dir),
            )
            pytest_output = proc.stdout + "\n" + proc.stderr
        except subprocess.TimeoutExpired:
            pytest_output = ""
            for tc in test_cases:
                results_detail.append(_build_result_entry(
                    tc, status="error",
                    error="Test execution timed out (120s)",
                ))
                _log_test_result(history, metrics, tc, "error", 120000,
                                 sim_mode=_sim_mode, sim_iteration=_sim_iteration,
                                 sim_seed=_sim_seed)
            continue
        except Exception as e:
            for tc in test_cases:
                results_detail.append(_build_result_entry(
                    tc, status="error", error=str(e),
                ))
                _log_test_result(history, metrics, tc, "error", 0,
                                 sim_mode=_sim_mode, sim_iteration=_sim_iteration,
                                 sim_seed=_sim_seed)
            continue

        # Parse pytest output and map results back to test cases
        test_results = _parse_pytest_output(pytest_output)
        _map_results_to_test_cases(
            test_cases, test_results, results_detail,
            history, metrics, protocol,
            sim_rng=_sim_rng, sim_fp_rate=_sim_fp_rate,
            sim_fn_rate=_sim_fn_rate, sim_mode=_sim_mode,
            sim_iteration=_sim_iteration, sim_seed=_sim_seed,
        )

    # ── Execute LLM-generated tests (standalone .py files, no template) ──
    for tc in llm_tests:
        ip_safe = tc.target_ip.replace(".", "_")
        filename = f"llm_test_{tc.test_id}_{ip_safe}.py"
        filepath = tests_dir / filename

        # Write standalone pytest code directly (IP already baked in by generator)
        filepath.write_text(tc.pytest_code, encoding="utf-8")

        try:
            proc = subprocess.run(
                ["pytest", filename, "-v", "--tb=short", "--no-header"],
                capture_output=True,
                text=True,
                timeout=120,
                cwd=str(tests_dir),
            )
            pytest_output = proc.stdout + "\n" + proc.stderr
            test_results = _parse_pytest_output(pytest_output)
            status = _find_matching_result(tc, test_results)
            if status is None and test_results:
                status = list(test_results.values())[0]
            if status is None:
                status = "FAILED"
        except subprocess.TimeoutExpired:
            status = "ERROR"
            results_detail.append(_build_result_entry(
                tc, status="error", error="LLM test timed out (120s)",
            ))
            _log_test_result(history, metrics, tc, "error", 120000,
                             sim_mode=_sim_mode, sim_iteration=_sim_iteration,
                             sim_seed=_sim_seed)
            continue
        except Exception as e:
            results_detail.append(_build_result_entry(
                tc, status="error", error=str(e),
            ))
            _log_test_result(history, metrics, tc, "error", 0,
                             sim_mode=_sim_mode, sim_iteration=_sim_iteration,
                             sim_seed=_sim_seed)
            continue

        vuln_found = (status == "PASSED")
        tc_status = "skipped" if status == "SKIPPED" else (
            "error" if status == "ERROR" else "completed"
        )

        # Simulation: FP/FN noise injection (same as registry tests)
        sim_noise_applied = None
        if _sim_rng and tc_status == "completed":
            if vuln_found and _sim_fn_rate > 0 and _sim_rng.random() < _sim_fn_rate:
                vuln_found = False
                sim_noise_applied = "false_negative"
            elif not vuln_found and _sim_fp_rate > 0 and _sim_rng.random() < _sim_fp_rate:
                vuln_found = True
                sim_noise_applied = "false_positive"

        results_detail.append(_build_result_entry(
            tc, status=tc_status, vulnerability_found=vuln_found,
            sim_noise=sim_noise_applied,
        ))
        _log_test_result(
            history, metrics, tc, tc_status, 0, vuln_found=vuln_found,
            sim_mode=_sim_mode, sim_iteration=_sim_iteration, sim_seed=_sim_seed,
        )

    if llm_tests:
        logging.info(
            f"[SuiteRunner] Executed {len(llm_tests)} LLM-generated tests"
        )

    elapsed_ms = int((time.time() - start_time) * 1000)

    result = {
        "status": "completed",
        "suite_id": suite.suite_id,
        "suite_name": suite.name,
        "tests_executed": metrics["tests_executed"],
        "vulns_detected": metrics["vulns_detected"],
        "execution_time_ms": elapsed_ms,
        "experiment_dir": str(experiment.root),
        "history_csv": str(experiment.path("history.csv")),
        "results": results_detail,
    }

    # Save metrics
    metrics_path = experiment.path("metrics_generated.json")
    with open(metrics_path, "w") as f:
        json.dump(result, f, indent=2, default=str)

    logging.info(
        f"[SuiteRunner] Suite '{suite.name}' completed: "
        f"{metrics['tests_executed']} tests, {metrics['vulns_detected']} vulns, "
        f"{elapsed_ms}ms"
    )

    return result


def _parse_pytest_output(output: str) -> dict:
    """
    Parse pytest -v output to extract per-test results.

    pytest -v output lines look like:
        test_file.py::test_function_name PASSED
        test_file.py::test_function_name FAILED
        test_file.py::test_function_name SKIPPED
        test_file.py::test_function_name ERROR

    In our templates:
      - PASSED = assert True → vulnerability confirmed
      - FAILED = pytest.fail() → no vulnerability found
      - SKIPPED = pytest.skip() → service unavailable
      - ERROR = exception during test

    Returns dict mapping lowercase function_name → status string.
    """
    results = {}
    for line in output.strip().split("\n"):
        line = line.strip()
        if not line or "::" not in line:
            continue

        for status_keyword in ["PASSED", "FAILED", "SKIPPED", "ERROR"]:
            if f" {status_keyword}" in line:
                # Extract function name: "test_file.py::test_func_name PASSED"
                parts = line.split("::")
                if len(parts) >= 2:
                    func_part = parts[-1].split()[0]  # "test_func_name"
                    func_name = func_part.strip().lower()
                    results[func_name] = status_keyword
                break

    return results


def _map_results_to_test_cases(
    test_cases, test_results, results_detail,
    history, metrics, protocol,
    sim_rng=None, sim_fp_rate=0.0, sim_fn_rate=0.0,
    sim_mode=None, sim_iteration=None, sim_seed=None,
):
    """
    Map pytest results back to TestCase objects. Each template may produce
    one or more test functions. We try to match test cases to pytest function
    names using the test_id or vuln_id.

    If the template produces a single function for all test cases of a protocol
    (e.g., http_test.py.j2 generates test_HTTP_DEFAULT_CREDENTIALS),
    we assign that result to all matching test cases.

    When simulation is active (sim_rng is not None), FP/FN noise is injected:
      - false_negative: a real vulnerability is masked (vuln_found flipped to False)
      - false_positive: a non-vulnerable test falsely reports a vulnerability
    """
    if not test_results:
        # pytest produced no parseable output — mark all as executed but unknown
        for tc in test_cases:
            results_detail.append(_build_result_entry(
                tc, status="completed", vulnerability_found=False,
            ))
            _log_test_result(history, metrics, tc, "completed", 0, vuln_found=False,
                             sim_mode=sim_mode, sim_iteration=sim_iteration,
                             sim_seed=sim_seed)
        return

    # Build lookup: try to match each tc.test_id to a pytest function name
    # The pytest function names come from the templates and may not match
    # test_ids exactly. We try several matching strategies.
    matched = set()

    for tc in test_cases:
        status = _find_matching_result(tc, test_results)

        if status is None and len(test_results) == 1:
            # Single-function template: assign its result to all test cases
            status = list(test_results.values())[0]

        if status is None:
            # No match found — if there are any results, use the overall outcome
            passed_count = sum(1 for v in test_results.values() if v == "PASSED")
            if passed_count > 0:
                status = "PASSED"
            else:
                status = "FAILED"

        vuln_found = status == "PASSED"
        tc_status = "skipped" if status == "SKIPPED" else (
            "error" if status == "ERROR" else "completed"
        )

        # ── Simulation: FP/FN noise injection ──
        sim_noise_applied = None
        if sim_rng and tc_status == "completed":
            if vuln_found and sim_fn_rate > 0 and sim_rng.random() < sim_fn_rate:
                vuln_found = False  # False negative: mask real vulnerability
                sim_noise_applied = "false_negative"
            elif not vuln_found and sim_fp_rate > 0 and sim_rng.random() < sim_fp_rate:
                vuln_found = True   # False positive: fake vulnerability
                sim_noise_applied = "false_positive"

        results_detail.append(_build_result_entry(
            tc, status=tc_status, vulnerability_found=vuln_found,
            sim_noise=sim_noise_applied,
        ))
        _log_test_result(
            history, metrics, tc, tc_status, 0, vuln_found=vuln_found,
            sim_mode=sim_mode, sim_iteration=sim_iteration, sim_seed=sim_seed,
        )


def _find_matching_result(tc, test_results: dict) -> str | None:
    """
    Try to match a TestCase to a pytest function result.
    Matching strategies (in order):
      1. Exact test_id match (lowercased)
      2. test_id is a substring of a function name
      3. Function name is a substring of test_id
    """
    tid = tc.test_id.lower()

    # Strategy 1: exact match
    if tid in test_results:
        return test_results[tid]

    # Also try with test_ prefix
    prefixed = f"test_{tid}"
    if prefixed in test_results:
        return test_results[prefixed]

    # Strategy 2: test_id is substring of function name
    for func_name, status in test_results.items():
        if tid in func_name:
            return status

    # Strategy 3: function name is substring of test_id
    for func_name, status in test_results.items():
        # Strip "test_" prefix for comparison
        clean_func = func_name.replace("test_", "", 1)
        if clean_func and clean_func in tid:
            return status

    return None


def _build_result_entry(tc, **extra) -> dict:
    """Build a result dict for a single test case."""
    entry = {
        "test_id": tc.test_id,
        "test_name": tc.test_name,
        "target": tc.target_ip,
        "port": tc.port,
        "protocol": tc.protocol,
        "severity": tc.severity,
        "is_recommended": getattr(tc, "is_recommended", False),
        "risk_score": getattr(tc, "risk_score", None),
    }
    entry.update(extra)
    return entry


# IP -> (device_type, firmware_version) mapping for IoT lab containers
_DEVICE_INFO = {
    "172.20.0.10": ("ftp_server",       "vsftpd-3.0.3"),
    "172.20.0.11": ("http_server",      "nginx-1.19.0"),
    "172.20.0.12": ("telnet_gateway",   "busybox-1.31.1"),
    "172.20.0.13": ("ftp_server",       "pure-ftpd-1.0.50"),
    "172.20.0.14": ("web_admin_panel",  "flask-2.0.1"),
    "172.20.0.15": ("http_server",      "httpd-2.4"),
    "172.20.0.16": ("mqtt_broker",      "mosquitto-2.0.15"),
    "172.20.0.17": ("ssh_server",       "openssh-6.6.1"),
    "172.20.0.20": ("ftp_server",       "pure-ftpd-1.0.49"),
    "172.20.0.21": ("coap_sensor",      "aiocoap-0.4.7"),
    "172.20.0.22": ("modbus_plc",       "pymodbus-3.5.2"),
    "172.20.0.23": ("http_api",         "flask-2.3.2"),
    "172.20.0.24": ("dns_server",       "dnslib-0.9.23"),
}


def _log_test_result(
    history, metrics, tc, status, elapsed_ms, vuln_found=False,
    sim_mode=None, sim_iteration=None, sim_seed=None,
):
    """Log a single test result to history CSV and update metrics."""
    metrics["tests_executed"] += 1

    if vuln_found:
        metrics["vulns_detected"] += 1

    dev_type, fw_version = _DEVICE_INFO.get(
        tc.target_ip, ("target", "unknown")
    )

    origin = getattr(tc, 'test_origin', 'registry')
    row = {
        "test_strategy": "llm_generated" if origin == "llm" else "generated",
        "container_id": tc.target_ip,
        "device_type": dev_type,
        "firmware_version": fw_version,
        "open_port": tc.port,
        "protocol": tc.protocol,
        "service": tc.protocol,
        "auth_required": tc.auth_required,
        "test_id": tc.test_id,
        "test_type": tc.vulnerability_type,
        "payload_size": 0,
        "timeout": 0,
        "vulnerability_found": int(vuln_found),
        "execution_time_ms": elapsed_ms,
        "simulation_mode": sim_mode or "unknown",
        "simulation_iteration": sim_iteration if sim_iteration is not None else -1,
        "simulation_seed": sim_seed if sim_seed is not None else 42,
    }

    history.log(row)


def _get_device_ports(suite: TestSuite, ip: str) -> list[int]:
    """Get all ports for a device from the suite."""
    for dev in suite.devices:
        if dev.get("ip") == ip:
            return [int(p) for p in dev.get("ports", [])]
    # Fallback: collect ports from test cases
    return sorted(set(tc.port for tc in suite.test_cases if tc.target_ip == ip))
