import xml.etree.ElementTree as ET


def parse_junit(xml_path):
    tree = ET.parse(xml_path)
    root = tree.getroot()

    results = {
        "passed": 0,
        "failed": 0,
        "skipped": 0
    }

    for testcase in root.iter("testcase"):
        if testcase.find("failure") is not None:
            results["failed"] += 1
        elif testcase.find("skipped") is not None:
            results["skipped"] += 1
        else:
            results["passed"] += 1

    return results
