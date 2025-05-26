from reports import Report
import json
import os

def report(report: Report):
    network = report.network
    devices = report.network.devices

    # Ensure the final extension is .json
    base_output = os.path.splitext(report.output)[0]
    filename = f"report/{report.timestamp}_vulnerability_report.json"

    data = {
        "timestamp": report.timestamp,
        "network": network.ip,
        "device_count": len(devices),
        "devices": []
    }

    for device in devices:
        data["devices"].append({
            "hostname": device.hostname or "N/A",
            "ip": device.ip,
            "mac": device.mac or "N/A",
            "open_ports": device.ports if device.ports else [],
            "vulnerabilities": device.vulnerabilities if hasattr(device, "vulnerabilities") else []
        })

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
