from reports import Report

def report(report: Report):

    network = report.network
    devices = report.network.devices

    with open(f"report/{report.timestamp}_{report.output}", "w", encoding='utf-8') as f:
        f.write(f"Scan Report - {report.timestamp}\n\n")
        f.write(f"Network: {network.ip}\n")
        f.write(f"Timestamp: {report.timestamp}\n\n")
        f.write(f"IoT Devices Found: {len(devices)}\n")
        f.write("-" * 40 + "\n")
        for device in devices:
            f.write(f"Hostname: {device.hostname}\n")
            f.write(f"IP: {device.ip}\n")
            f.write(f"MAC: {device.mac}\n")
            f.write(f"Open Ports: {device.ports}\n")
            f.write("-" * 40 + "\n")
