from reports import Report
import csv
import os

def report(report: Report):
    network = report.network
    devices = report.network.devices

    # Ensure the extension is .csv
    base_output = os.path.splitext(report.output)[0]
    filename = f"report/{report.timestamp}_{base_output}.csv"

    with open(filename, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)

        # Header
        writer.writerow(["Hostname", "IP", "MAC", "Open Ports", "Network", "Timestamp"])

        # Device data
        for device in devices:
            writer.writerow([
                device.hostname or "N/A",
                device.ip,
                device.mac or "N/A",
                ", ".join(map(str, device.ports)) if device.ports else "None",
                network.ip,
                report.timestamp
            ])
