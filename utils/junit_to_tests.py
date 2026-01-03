import xml.etree.ElementTree as ET
from dataclasses import dataclass


@dataclass
class TestResult:
    name: str
    vuln_id: str
    status: str
    duration: float


def parse_junit_tests(junit_xml):
    tree = ET.parse(junit_xml)
    root = tree.getroot()

    results = []

    for case in root.iter("testcase"):
        name = case.attrib.get("name")
        duration = float(case.attrib.get("time", 0))

        if case.find("failure") is not None:
            status = "FAIL"
        elif case.find("skipped") is not None:
            status = "SKIP"
        else:
            status = "PASS"

        # Extrai o ID da vulnerabilidade do nome do teste
        vuln_id = extract_vuln_id(name)

        results.append(
            TestResult(
                name=name,
                vuln_id=vuln_id,
                status=status,
                duration=duration
            )
        )

    return results


def extract_vuln_id(test_name):
    """
    Espera nomes no formato:
    test_<VULN_ID>_descricao
    """
    parts = test_name.split("_")
    for p in parts:
        if p.isupper():
            return p
    return "UNKNOWN"
