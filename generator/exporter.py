"""
Test Suite Exporter — exports TestSuites as JSON, YAML, or executable Python (pytest).
"""
import json
import os
import logging
from pathlib import Path
from typing import Optional

import yaml
from jinja2 import Environment, FileSystemLoader

from models.test_case import TestSuite


TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "..", "templates")


def export_json(suite: TestSuite) -> str:
    """Export test suite as JSON specification."""
    return json.dumps(suite.to_dict(), indent=2, default=str)


def export_yaml(suite: TestSuite) -> str:
    """Export test suite as YAML specification."""
    return yaml.dump(suite.to_dict(), default_flow_style=False, sort_keys=False)


def export_python(suite: TestSuite) -> str:
    """
    Export test suite as a single executable pytest file.
    Groups tests by protocol and renders them using Jinja2 templates.
    """
    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))

    # Group test cases by protocol
    by_protocol = {}
    for tc in suite.test_cases:
        by_protocol.setdefault(tc.protocol, []).append(tc)

    output_parts = [
        '"""',
        f'Auto-generated IoT Vulnerability Test Suite: {suite.name}',
        f'Suite ID: {suite.suite_id}',
        f'Generated: {suite.created_at}',
        f'Total tests: {suite.total_tests}',
        '"""',
        'import pytest',
        'import socket',
        'import requests',
        '',
        'TIMEOUT = 5',
        '',
    ]

    for protocol, test_cases in sorted(by_protocol.items()):
        output_parts.append(f'# === {protocol.upper()} Tests ===')
        output_parts.append('')

        for tc in test_cases:
            func_name = f"test_{tc.test_id}_{tc.target_ip.replace('.', '_')}_port{tc.port}"
            output_parts.append(f'@pytest.mark.vuln_id("{tc.test_id}")')
            output_parts.append(f'@pytest.mark.severity("{tc.severity}")')
            output_parts.append(f'def {func_name}():')
            output_parts.append(f'    """{tc.test_name} - {tc.description}')
            output_parts.append(f'    Target: {tc.target_ip}:{tc.port}')
            output_parts.append(f'    OWASP: {tc.owasp_iot_category}')
            output_parts.append(f'    Severity: {tc.severity}')
            if tc.risk_score is not None:
                output_parts.append(f'    Risk Score: {tc.risk_score:.2f}')
            output_parts.append(f'    """')
            output_parts.append(f'    ip = "{tc.target_ip}"')
            output_parts.append(f'    port = {tc.port}')
            output_parts.append(f'    # Test steps:')
            for step in tc.test_steps:
                output_parts.append(f'    # - {step}')
            output_parts.append(f'    # Expected: {tc.expected_result}')
            output_parts.append(f'    pytest.skip("Execute via Emergence framework for full implementation")')
            output_parts.append('')

    return '\n'.join(output_parts)


def export_python_files(suite: TestSuite, outdir: Path) -> list[str]:
    """
    Export test suite as individual pytest files per protocol.
    Uses Jinja2 templates when available, falls back to generic generation.
    Returns list of created file paths.
    """
    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    # Group test cases by protocol
    by_protocol = {}
    for tc in suite.test_cases:
        by_protocol.setdefault(tc.protocol, []).append(tc)

    created_files = []

    for protocol, test_cases in by_protocol.items():
        # Group by target IP within each protocol
        by_target = {}
        for tc in test_cases:
            by_target.setdefault(tc.target_ip, []).append(tc)

        for target_ip, target_tests in by_target.items():
            ip_safe = target_ip.replace(".", "_")
            filename = f"test_{protocol}_{ip_safe}.py"
            filepath = outdir / filename

            # Try protocol-specific template
            template_name = f"{protocol}_test.py.j2"
            try:
                template = env.get_template(template_name)
                ports = sorted(set(str(tc.port) for tc in target_tests))
                content = template.render(
                    ip=target_ip,
                    ports=",".join(ports),
                    test_cases=target_tests,
                    suite_name=suite.name,
                    suite_id=suite.suite_id,
                )
            except Exception:
                # Fallback to generic generation
                content = _generate_generic_test_file(protocol, target_ip, target_tests, suite)

            filepath.write_text(content, encoding="utf-8")
            created_files.append(str(filepath))

    logging.info(f"[Exporter] Created {len(created_files)} test files in {outdir}")
    return created_files


def _generate_generic_test_file(
    protocol: str, target_ip: str, test_cases: list, suite: TestSuite
) -> str:
    """Generate a generic pytest file when no specific template exists."""
    lines = [
        f'"""Auto-generated {protocol.upper()} tests for {target_ip}"""',
        'import pytest',
        'import socket',
        '',
        'TIMEOUT = 5',
        '',
    ]

    for tc in test_cases:
        func_name = f"test_{tc.test_id}"
        lines.append(f'@pytest.mark.vuln_id("{tc.test_id}")')
        lines.append(f'@pytest.mark.severity("{tc.severity}")')
        lines.append(f'def {func_name}():')
        lines.append(f'    """{tc.description}"""')
        lines.append(f'    ip = "{tc.target_ip}"')
        lines.append(f'    port = {tc.port}')
        lines.append(f'    try:')
        lines.append(f'        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)')
        lines.append(f'        sock.settimeout(TIMEOUT)')
        lines.append(f'        sock.connect((ip, port))')
        lines.append(f'        sock.close()')
        lines.append(f'        assert True  # Port accessible')
        lines.append(f'    except Exception:')
        lines.append(f'        pytest.fail("Service not accessible")')
        lines.append('')

    return '\n'.join(lines)
