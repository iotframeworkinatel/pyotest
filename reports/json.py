from reports import Report
import json
import os

def report(report: Report):
    network = report.network
    devices = report.network.devices

    # Garante que a extensão final seja .json
    base_output = os.path.splitext(report.output)[0]
    filename = f"report/{report.timestamp}_{base_output}.json"

    data = {
        "timestamp": report.timestamp,
        "rede": network.ip,
        "quantidade_dispositivos": len(devices),
        "dispositivos": []
    }

    for device in devices:
        data["dispositivos"].append({
            "hostname": device.hostname or "N/A",
            "ip": device.ip,
            "mac": device.mac or "N/A",
            "portas_abertas": device.ports if device.ports else []
        })

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
