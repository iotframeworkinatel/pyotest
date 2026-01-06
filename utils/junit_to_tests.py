from dataclasses import dataclass
import xml.etree.ElementTree as ET


@dataclass
class TestResult:
    name: str
    classname: str
    vuln_id: str
    status: str        # PASS | FAIL | SKIP
    duration: float


def parse_junit_tests(junit_xml_path):
    """
    Converte relatório JUnit XML em resultados semânticos:
    PASS  -> vulnerabilidade confirmada
    FAIL  -> vulnerabilidade não encontrada
    SKIP  -> erro / ambiente / não testável
    """

    results = []

    tree = ET.parse(junit_xml_path)
    root = tree.getroot()

    for testcase in root.iter("testcase"):
        name = testcase.attrib.get("name", "UNKNOWN")
        classname = testcase.attrib.get("classname", "")
        duration = float(testcase.attrib.get("time", 0.0))

        vuln_id = "UNKNOWN"

        # Extração robusta do vuln_id
        for line in testcase.itertext():
            if "vuln_id" in line:
                # Ex: @pytest.mark.vuln_id("FTP_ANON_LOGIN")
                try:
                    vuln_id = line.split("vuln_id")[1].split('"')[1]
                except Exception:
                    pass

        # --- CLASSIFICAÇÃO SEMÂNTICA ---
        if testcase.find("skipped") is not None:
            status = "SKIP"

        elif testcase.find("error") is not None:
            # erro de execução → NÃO é falha lógica
            status = "SKIP"

        elif testcase.find("failure") is not None:
            # assert falhou → vulnerabilidade NÃO existe
            status = "FAIL"

        else:
            # passou sem erros → vulnerabilidade CONFIRMADA
            status = "PASS"

        results.append(
            TestResult(
                name=name,
                classname=classname,
                vuln_id=vuln_id,
                status=status,
                duration=duration,
            )
        )

    return results
