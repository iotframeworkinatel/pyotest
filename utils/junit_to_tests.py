import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path


@dataclass
class TestResult:
    host: str
    test_type: str
    status: str  # PASS | FAIL | SKIP


def normalize_test_type(name: str) -> str:
    name = name.upper()

    if "FTP" in name:
        return "FTP_WEAK_OR_ANON_LOGIN"
    if "SSH" in name:
        return "SSH_WEAK_CREDENTIALS"
    if "TELNET" in name:
        return "TELNET_OPEN"
    if "MQTT" in name:
        return "MQTT_ANONYMOUS_ACCESS"
    if "HTTP" in name:
        return "HTTP_DEFAULT_CREDENTIALS"

    return "BANNER_GENERIC"


def extract_host(classname: str) -> str:
    # exemplo: generated_tests.test_172_20_0_10_xxx
    parts = classname.split("_")
    for i in range(len(parts)):
        if parts[i].isdigit():
            return ".".join(parts[i:i+4])
    return "UNKNOWN"


def parse_junit_tests(xml_path: Path):
    tree = ET.parse(xml_path)
    root = tree.getroot()

    results = []

    for tc in root.iter("testcase"):
        classname = tc.attrib.get("classname", "")
        name = tc.attrib.get("name", "")

        host = extract_host(classname)
        test_type = normalize_test_type(name)

        if tc.find("skipped") is not None:
            status = "SKIP"
        elif tc.find("failure") is not None or tc.find("error") is not None:
            status = "FAIL"
        else:
            status = "PASS"

        results.append(TestResult(
            host=host,
            test_type=test_type,
            status=status
        ))

    return results
