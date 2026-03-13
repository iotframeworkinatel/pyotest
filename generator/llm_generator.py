"""
LLM-Based Test Case Generator

Uses pluggable LLM providers (Claude, OpenAI, Gemini) to generate novel
pytest security test functions for IoT devices. Generated tests target
specific CVEs and vulnerability classes not covered by the static test
registry.

Each generated test:
- Is a standalone pytest function with @pytest.mark.vuln_id decorator
- Uses only allowed imports (validated by llm_validator.py)
- Targets a specific CVE or vulnerability class
- Includes proper timeout handling
- Uses assert True = vulnerability confirmed, pytest.fail() = not found

Integration: Generated tests are validated via AST, written to experiment
directories, executed via pytest alongside registry tests, and tagged with
test_strategy="llm_generated" in history.csv.
"""
import logging
import os
import time
from typing import Optional

from generator.llm_validator import validate_generated_test, validate_multiple_tests


# System prompt for security test generation
SYSTEM_PROMPT = """You are an expert IoT security researcher and penetration tester.
Your task is to generate novel pytest security test functions for IoT devices.

Context:
- You are testing devices in a controlled IoT security lab (Docker containers)
- Tests run against simulated vulnerable IoT services (FTP, HTTP, Telnet, MQTT, SSH, CoAP, Modbus, DNS)
- OWASP IoT Top 10 is your reference framework
- Tests must be safe to run in a contained lab environment

Conventions:
- Each test is a standalone pytest function named test_<protocol>_<vuln_type>_<id>
- Use @pytest.mark.vuln_id("<unique_id>") decorator for tracking
- assert True = vulnerability confirmed (PASSED in pytest = vuln found)
- pytest.fail("description") = vulnerability not found
- All network operations must have timeout=5 (seconds)
- Include a docstring explaining the vulnerability being tested
- Handle connection errors gracefully (try/except with pytest.fail)

Available Python libraries:
- requests (HTTP/HTTPS)
- paramiko (SSH/SFTP)
- paho.mqtt.client (MQTT)
- aiocoap (CoAP, use asyncio)
- pymodbus (Modbus TCP)
- socket, ssl, struct (raw networking)
- json, base64, hashlib, time, re

IMPORTANT: Do NOT use os, subprocess, shutil, sys, or any file-writing operations.
Tests must ONLY perform network operations against the target device."""


def _build_user_prompt(
    device_ip: str,
    open_ports: list[int],
    protocols: list[str],
    existing_test_ids: list[str],
    max_tests: int = 10,
) -> str:
    """Build the user prompt for test generation."""
    return f"""Generate {max_tests} novel pytest security test functions for an IoT device
at {device_ip} with open ports {open_ports} running {protocols}.

Each test must:
1. Be a standalone pytest function with @pytest.mark.vuln_id decorator
2. Use only allowed imports: requests, paramiko, paho.mqtt.client, aiocoap, pymodbus, socket, ssl, struct
3. Target a specific CVE or vulnerability class NOT covered by existing tests: {existing_test_ids[:20]}
4. Include proper timeout handling (5s default)
5. Use assert True for vulnerability confirmed, pytest.fail() for not found
6. Include docstring explaining the vulnerability being tested
7. Handle ConnectionError, TimeoutError gracefully

Return as a JSON array where each element has these fields:
- test_id: unique identifier like "llm_<protocol>_<vuln_short_name>"
- test_name: human-readable name
- pytest_code: complete Python code for the test function (including imports)
- vulnerability_type: category (e.g., "authentication_bypass", "buffer_overflow", "information_disclosure")
- severity: one of "critical", "high", "medium", "low", "info"
- references: list of CVE IDs or URLs if applicable

Focus on vulnerability classes like:
- Default/weak credentials
- Protocol-specific attacks (MQTT topic injection, Modbus function code abuse, CoAP observe flooding)
- Information disclosure via service banners or debug endpoints
- Authentication bypass attempts
- Buffer overflow / fuzzing patterns
- Insecure configurations"""


# Tool schema for structured output
TEST_GENERATION_TOOL = {
    "name": "generate_security_tests",
    "description": "Generate a list of pytest security test functions for IoT devices",
    "input_schema": {
        "type": "object",
        "properties": {
            "tests": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "test_id": {
                            "type": "string",
                            "description": "Unique test identifier like llm_http_cve_2023_1234"
                        },
                        "test_name": {
                            "type": "string",
                            "description": "Human-readable test name"
                        },
                        "pytest_code": {
                            "type": "string",
                            "description": "Complete pytest function code including imports"
                        },
                        "vulnerability_type": {
                            "type": "string",
                            "description": "Vulnerability category"
                        },
                        "severity": {
                            "type": "string",
                            "enum": ["critical", "high", "medium", "low", "info"]
                        },
                        "references": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "CVE IDs or reference URLs"
                        }
                    },
                    "required": ["test_id", "test_name", "pytest_code", "vulnerability_type", "severity"]
                }
            }
        },
        "required": ["tests"]
    }
}


class LLMTestGenerator:
    """Generates novel pytest security tests using a pluggable LLM provider."""

    def __init__(self, provider: str = "claude"):
        """Initialize the LLM test generator.

        Args:
            provider: Provider ID — "claude", "openai", or "gemini".
        """
        from generator.llm_providers.registry import get_provider
        self._provider = get_provider(provider)
        self._provider_id = provider

    def is_available(self) -> bool:
        """Check if the selected LLM provider is available (API key set)."""
        return self._provider.is_available()

    def generate_tests_for_device(
        self,
        device_ip: str,
        open_ports: list[int],
        protocols: list[str],
        existing_tests: Optional[list[str]] = None,
        simulation_state: Optional[dict] = None,
        max_tests: int = 10,
    ) -> list[dict]:
        """Generate novel test cases not in existing registry.

        Args:
            device_ip: Target device IP address.
            open_ports: List of open ports on the device.
            protocols: List of protocols running on the device.
            existing_tests: Test IDs already in the registry (to avoid duplication).
            simulation_state: Current environment state for adaptation.
            max_tests: Maximum number of tests to generate.

        Returns:
            List of validated test dicts with fields:
            {test_id, test_name, pytest_code, vulnerability_type, severity, references}
        """
        if not self.is_available():
            logging.warning("[LLMGenerator] Provider not available, skipping generation")
            return []

        existing_test_ids = existing_tests or []
        user_prompt = _build_user_prompt(
            device_ip, open_ports, protocols, existing_test_ids, max_tests
        )

        try:
            start = time.time()
            tests = self._provider.generate(
                system_prompt=SYSTEM_PROMPT,
                user_prompt=user_prompt,
                output_schema=TEST_GENERATION_TOOL,
                max_tokens=8192,
            )
            elapsed = time.time() - start

            if not tests:
                logging.warning("[LLMGenerator] No tests returned from provider")
                return []

            logging.info(
                f"[LLMGenerator] Generated {len(tests)} tests for {device_ip} "
                f"in {elapsed:.1f}s (provider={self._provider_id})"
            )

            # Validate all generated tests via AST
            validated = validate_multiple_tests(tests)

            # Tag with origin metadata
            for test in validated:
                test["test_origin"] = "llm"
                test["test_strategy"] = "llm_generated"
                test["device_ip"] = device_ip
                test["provider"] = self._provider_id

            return validated

        except Exception as e:
            logging.error(f"[LLMGenerator] Generation failed: {e}")
            return []

    def generate_tests_for_gaps(
        self,
        gaps: dict,
        devices: list[dict],
        existing_test_ids: list[str],
        execution_context: str = "",
        max_tests: int = 10,
    ) -> list[dict]:
        """Generate tests specifically targeting identified coverage gaps.

        Args:
            gaps: Output from detect_coverage_gaps().
            devices: List of device dicts with ip, ports, protocols.
            existing_test_ids: All existing test IDs.
            execution_context: Summary of current experiment state.
            max_tests: Maximum total tests to generate.

        Returns:
            Combined list of validated test dicts targeting gap areas.
        """
        if not self.is_available():
            return []

        # Build a gap-aware prompt supplement
        gap_context_parts = []
        if gaps.get("low_detection_protocols"):
            protos = [p["protocol"] for p in gaps["low_detection_protocols"]]
            gap_context_parts.append(
                f"Protocols with near-zero detection rates: {protos}. "
                "Focus on these protocols with novel attack vectors."
            )
        if gaps.get("underrepresented_protocols"):
            gap_context_parts.append(
                f"Underrepresented protocols needing more tests: "
                f"{gaps['underrepresented_protocols']}"
            )
        if gaps.get("suggested_focus_areas"):
            gap_context_parts.append(
                f"Suggested vulnerability classes to target: "
                f"{gaps['suggested_focus_areas'][:10]}"
            )
        if gaps.get("zero_detection_tests"):
            gap_context_parts.append(
                f"Tests that NEVER found vulnerabilities (avoid similar approaches): "
                f"{gaps['zero_detection_tests'][:10]}"
            )
        if execution_context:
            gap_context_parts.append(f"Current experiment state: {execution_context}")

        gap_supplement = "\n".join(gap_context_parts)

        # Distribute tests across gap protocols, falling back to all devices
        all_tests = []
        gap_protocols = set(
            p["protocol"] for p in gaps.get("low_detection_protocols", [])
        ) | set(gaps.get("underrepresented_protocols", []))

        for device in devices:
            ip = device.get("ip") or device.get("target_ip", "")
            ports = device.get("open_ports", device.get("ports", []))
            protocols = device.get("protocols", [])

            if not ip or not ports:
                continue

            # Prioritize gap protocols for this device
            device_gap_protos = [p for p in protocols if p in gap_protocols]
            if not device_gap_protos and not gap_protocols:
                device_gap_protos = protocols

            if not device_gap_protos:
                continue

            per_device = max(2, max_tests // max(len(devices), 1))
            device_tests = self.generate_tests_for_device(
                device_ip=ip,
                open_ports=[int(p) for p in ports],
                protocols=device_gap_protos,
                existing_tests=existing_test_ids + [t["test_id"] for t in all_tests],
                max_tests=per_device,
            )
            all_tests.extend(device_tests)

            if len(all_tests) >= max_tests:
                break

        logging.info(
            f"[LLMGenerator] Gap-targeted: {len(all_tests)} tests for "
            f"{len(gap_protocols)} gap protocols"
        )
        return all_tests[:max_tests]

    def generate_tests_for_suite(
        self,
        devices: list[dict],
        existing_test_ids: list[str],
        max_tests_per_device: int = 5,
    ) -> list[dict]:
        """Generate tests for all devices in a suite.

        Args:
            devices: List of device dicts with ip, ports, protocols.
            existing_test_ids: All existing test IDs.
            max_tests_per_device: Max tests per device.

        Returns:
            Combined list of all validated tests.
        """
        all_tests = []
        for device in devices:
            ip = device.get("ip") or device.get("target_ip", "")
            ports = device.get("open_ports", [])
            protocols = device.get("protocols", [])

            if not ip or not ports:
                continue

            device_tests = self.generate_tests_for_device(
                device_ip=ip,
                open_ports=ports,
                protocols=protocols,
                existing_tests=existing_test_ids + [t["test_id"] for t in all_tests],
                max_tests=max_tests_per_device,
            )
            all_tests.extend(device_tests)

        logging.info(
            f"[LLMGenerator] Total: {len(all_tests)} validated tests "
            f"for {len(devices)} devices"
        )
        return all_tests


def write_llm_tests_to_file(
    tests: list[dict],
    output_dir: str,
    prefix: str = "llm_test",
) -> list[str]:
    """Write validated LLM-generated tests to pytest files.

    Each test is written to a separate file for isolated execution.

    Args:
        tests: List of validated test dicts with pytest_code.
        output_dir: Directory to write test files.
        prefix: File name prefix.

    Returns:
        List of written file paths.
    """
    os.makedirs(output_dir, exist_ok=True)
    written = []

    for test in tests:
        code = test.get("pytest_code", "")
        test_id = test.get("test_id", f"unknown_{len(written)}")

        if not code:
            continue

        # Validate one more time before writing
        is_valid, violations = validate_generated_test(code)
        if not is_valid:
            logging.warning(
                f"[LLMGenerator] Skipping invalid test {test_id}: {violations[:2]}"
            )
            continue

        filename = f"{prefix}_{test_id}.py"
        filepath = os.path.join(output_dir, filename)

        with open(filepath, "w") as f:
            f.write(f"# Auto-generated by LLM Test Generator\n")
            f.write(f"# Test ID: {test_id}\n")
            f.write(f"# Vulnerability: {test.get('vulnerability_type', 'unknown')}\n")
            f.write(f"# Severity: {test.get('severity', 'unknown')}\n")
            f.write(f"# References: {test.get('references', [])}\n\n")
            f.write(code)
            f.write("\n")

        written.append(filepath)
        logging.debug(f"[LLMGenerator] Wrote test file: {filepath}")

    logging.info(f"[LLMGenerator] Wrote {len(written)} test files to {output_dir}")
    return written


# ── Coverage Gap Detection ──────────────────────────────────────────────


def detect_coverage_gaps(
    history_df,
    existing_test_ids: list[str],
    min_iterations: int = 3,
) -> dict:
    """Analyze execution history to find where new tests are needed.

    Args:
        history_df: DataFrame with columns: protocol, test_id, vulnerability_found,
                    simulation_iteration, test_strategy.
        existing_test_ids: Test IDs currently in the suite.
        min_iterations: Minimum iterations of data required for gap analysis.

    Returns:
        {
            "low_detection_protocols": [{"protocol": str, "detection_rate": float, "n_tests": int}],
            "zero_detection_tests": [str],
            "underrepresented_protocols": [str],
            "suggested_focus_areas": [str],
        }
    """
    import pandas as pd

    if history_df is None or len(history_df) == 0:
        return {"low_detection_protocols": [], "zero_detection_tests": [],
                "underrepresented_protocols": [], "suggested_focus_areas": []}

    df = history_df.copy()
    df["vulnerability_found"] = pd.to_numeric(
        df["vulnerability_found"], errors="coerce"
    ).fillna(0).astype(int)

    n_iterations = df["simulation_iteration"].nunique() if "simulation_iteration" in df.columns else 0
    if n_iterations < min_iterations:
        return {"low_detection_protocols": [], "zero_detection_tests": [],
                "underrepresented_protocols": [], "suggested_focus_areas": []}

    # 1. Per-protocol detection rates
    low_detection = []
    if "protocol" in df.columns:
        proto_stats = df.groupby("protocol").agg(
            detection_rate=("vulnerability_found", "mean"),
            n_tests=("vulnerability_found", "count"),
        ).reset_index()
        for _, row in proto_stats.iterrows():
            if row["detection_rate"] < 0.1:
                low_detection.append({
                    "protocol": row["protocol"],
                    "detection_rate": round(float(row["detection_rate"]), 4),
                    "n_tests": int(row["n_tests"]),
                })

    # 2. Tests that never found a vulnerability
    zero_tests = []
    if "test_id" in df.columns:
        test_stats = df.groupby("test_id")["vulnerability_found"].sum()
        zero_tests = [tid for tid, total in test_stats.items()
                      if total == 0 and tid in existing_test_ids]

    # 3. Underrepresented protocols (few test cases relative to others)
    underrepresented = []
    if "protocol" in df.columns:
        proto_counts = df.groupby("protocol")["test_id"].nunique()
        if len(proto_counts) > 1:
            median_count = proto_counts.median()
            for proto, count in proto_counts.items():
                if count < median_count * 0.5:
                    underrepresented.append(proto)

    # 4. Build suggested focus areas
    focus_areas = []
    _vuln_type_map = {
        "http": ["injection", "XSS", "SSRF", "insecure deserialization", "API abuse"],
        "mqtt": ["topic injection", "message spoofing", "QoS abuse", "retain poisoning"],
        "ftp": ["bounce attack", "credential stuffing", "PASV abuse"],
        "ssh": ["key exchange downgrade", "username enumeration", "algorithm negotiation"],
        "coap": ["observe flooding", "block-wise transfer abuse", "multicast amplification"],
        "modbus": ["function code abuse", "coil manipulation", "register overwrite"],
        "telnet": ["command injection", "environment variable injection"],
        "dns": ["zone transfer", "cache poisoning", "amplification"],
    }
    for item in low_detection:
        proto = item["protocol"]
        if proto in _vuln_type_map:
            focus_areas.extend(
                f"{proto}: {v}" for v in _vuln_type_map[proto][:2]
            )
    for proto in underrepresented:
        if proto in _vuln_type_map:
            focus_areas.append(f"{proto}: expand coverage")

    return {
        "low_detection_protocols": low_detection,
        "zero_detection_tests": zero_tests[:20],  # cap to avoid huge prompts
        "underrepresented_protocols": underrepresented,
        "suggested_focus_areas": focus_areas,
    }
