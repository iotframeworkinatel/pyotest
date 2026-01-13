import time
from utils.normalize import normalize_result


def run_and_log(
    *,
    test_func,
    test_id,
    test_type,
    device,
    port,
    protocol,
    history,
    metrics,
    args=None,
    strategy="static",
    auth_required=False,
):
    """
    Generic executor for all vulnerability tests (static and AutoML).
    """

    metrics["tests_executed"] += 1

    start = time.time()
    try:
        if args:
            result = test_func(device.ip, port, args=args)
        else:
            result = test_func(device.ip, port)
    except Exception:
        result = None

    elapsed = int((time.time() - start) * 1000)
    vuln = normalize_result(result)

    history.log({
        "test_strategy": strategy,
        "container_id": device.ip,
        "device_type": getattr(device, "device_type", "unknown"),
        "firmware_version": getattr(device, "os", "unknown"),
        "open_port": port,
        "protocol": protocol,
        "service": protocol,
        "auth_required": auth_required,
        "test_id": test_id,
        "test_type": test_type,
        "payload_size": 0,
        "timeout": 0,
        "vulnerability_found": vuln,
        "execution_time_ms": elapsed
    })

    if vuln:
        metrics["vulns_detected"] += 1
        device.vulnerabilities.append(
            f"[{strategy.upper()}] {test_id} vulnerability found"
        )

    return vuln
