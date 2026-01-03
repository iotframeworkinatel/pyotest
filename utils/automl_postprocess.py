import xml.etree.ElementTree as ET


def apply_automl_results(iot_devices, junit_xml):
    tree = ET.parse(junit_xml)
    root = tree.getroot()

    confirmed_vulns = set()

    for case in root.iter("testcase"):
        if case.find("failure") is None and case.find("skipped") is None:
            for prop in case.iter("property"):
                if prop.attrib.get("name") == "vuln_id":
                    confirmed_vulns.add(prop.attrib["value"])

    for device in iot_devices:
        device.vulnerabilities = [
            v for v in device.vulnerabilities
            if v in confirmed_vulns
        ]

