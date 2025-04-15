from reports import Report
import csv
import os

def report(report: Report):
    network = report.network
    devices = report.network.devices

    # Garante que a extensão seja .csv
    base_output = os.path.splitext(report.output)[0]
    filename = f"report/{report.timestamp}_{base_output}.csv"

    with open(filename, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)

        # Cabeçalho
        writer.writerow(["Hostname", "IP", "MAC", "Portas Abertas", "Rede", "Data"])

        # Dados dos dispositivos
        for device in devices:
            writer.writerow([
                device.hostname or "N/A",
                device.ip,
                device.mac or "N/A",
                ", ".join(map(str, device.ports)) if device.ports else "Nenhuma",
                network.ip,
                report.timestamp
            ])
