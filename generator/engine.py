"""
Test Case Generation Engine — generates TestSuites from device/protocol selections.
"""
import logging
from typing import Optional

from models.test_case import TestCase, TestSuite
from generator.registry import TEST_REGISTRY, get_tests_for_protocol
from generator.owasp_mapping import get_owasp_category, get_severity
from utils.protocols import PORT_PROTOCOL_MAP


def generate_test_suite(
    devices: list[dict],
    selected_protocols: Optional[list[str]] = None,
    severity_filter: Optional[list[str]] = None,
    include_uncommon: bool = True,
    name: str = "",
) -> TestSuite:
    """
    Generate a TestSuite for the given devices and protocol selection.

    Args:
        devices: List of dicts with keys: ip, ports (list[int]), and optionally protocols
        selected_protocols: Filter to only these protocols (None = all discovered)
        severity_filter: Filter to only these severity levels
        include_uncommon: Whether to include uncommon/advanced tests
        name: Optional suite name
    """
    test_cases = []
    device_summaries = []

    for device in devices:
        ip = device.get("ip", "")
        ports = device.get("ports", [])

        # Resolve ports to protocols
        device_protocols = set()
        port_protocol_pairs = []
        for port in ports:
            proto = PORT_PROTOCOL_MAP.get(int(port), "generic")
            if proto != "generic":
                device_protocols.add(proto)
                port_protocol_pairs.append((int(port), proto))

        device_summaries.append({
            "ip": ip,
            "ports": ports,
            "protocols": sorted(device_protocols),
        })

        # Filter protocols
        active_protocols = device_protocols
        if selected_protocols:
            active_protocols = device_protocols & set(selected_protocols)

        # Generate tests for each port/protocol pair
        for port, protocol in port_protocol_pairs:
            if protocol not in active_protocols:
                continue

            registry_tests = get_tests_for_protocol(protocol)
            for test_def in registry_tests:
                # Filter by common/uncommon
                if not include_uncommon and "uncommon" in test_def.get("tags", []):
                    continue

                # Filter by severity
                severity = test_def.get("severity", get_severity(test_def["vulnerability_type"]))
                if severity_filter and severity not in severity_filter:
                    continue

                tc = TestCase(
                    test_id=test_def["test_id"],
                    test_name=test_def["test_name"],
                    description=test_def["description"],
                    protocol=protocol,
                    port=port,
                    target_ip=ip,
                    vulnerability_type=test_def["vulnerability_type"],
                    owasp_iot_category=get_owasp_category(test_def["vulnerability_type"]),
                    severity=severity,
                    test_steps=test_def.get("test_steps", []),
                    expected_result=test_def.get("expected_result", ""),
                    payloads=test_def.get("payloads", []),
                    references=test_def.get("references", []),
                    auth_required=test_def.get("auth_required", False),
                    tags=test_def.get("tags", []),
                )
                test_cases.append(tc)

    # Deduplicate (same test_id + target_ip + port)
    seen = set()
    unique_tests = []
    for tc in test_cases:
        key = (tc.test_id, tc.target_ip, tc.port)
        if key not in seen:
            seen.add(key)
            unique_tests.append(tc)

    suite = TestSuite(
        name=name or f"IoT Test Suite ({len(unique_tests)} tests)",
        devices=device_summaries,
        test_cases=unique_tests,
        metadata={
            "selected_protocols": selected_protocols,
            "severity_filter": severity_filter,
            "include_uncommon": include_uncommon,
        },
    )

    logging.info(
        f"[Generator] Created suite '{suite.name}' with {suite.total_tests} tests "
        f"for {len(devices)} device(s), protocols: {suite.protocols}"
    )

    return suite
