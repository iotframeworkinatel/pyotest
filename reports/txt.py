from reports import Report

def report(report: Report):

    network = report.network
    devices = report.network.devices

    with open(f"report/{report.timestamp}_{report.output}", "w", encoding='utf-8') as f:
            f.write(f"Relatório de escaneamento - {report.timestamp}\n\n")
            f.write(f"Rede: {network.ip}\n")    
            f.write(f"Data: {report.timestamp}\n\n")
            f.write(f"Dispositivos iot encontrados: {len(devices)}\n")
            f.write("-" * 40 + "\n")
            for device in devices:
                f.write(f"Hostname: {device.hostname}\n")
                f.write(f"IP: {device.ip}\n")
                f.write(f"MAC: {device.mac}\n")
                f.write(f"Portas abertas: {device.ports}\n")
                f.write("-" * 40 + "\n")