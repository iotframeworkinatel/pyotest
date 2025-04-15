from reports import Report
import os

def report(report: Report):
    network = report.network
    devices = report.network.devices

    # Garante que a extensão final seja .html
    base_output = os.path.splitext(report.output)[0]
    filename = f"report/{report.timestamp}_{base_output}.html"

    with open(filename, "w", encoding="utf-8") as f:
        f.write("<!DOCTYPE html>\n")
        f.write("<html lang='pt-BR'>\n")
        f.write("<head>\n")
        f.write("    <meta charset='UTF-8'>\n")
        f.write("    <title>Relatório de Escaneamento</title>\n")
        f.write("    <style>\n")
        f.write("        body { font-family: Arial, sans-serif; margin: 40px; }\n")
        f.write("        h1 { color: #2c3e50; }\n")
        f.write("        .info { margin-bottom: 20px; }\n")
        f.write("        .device { border: 1px solid #ccc; padding: 15px; border-radius: 6px; margin-bottom: 20px; }\n")
        f.write("        .device p { margin: 5px 0; }\n")
        f.write("    </style>\n")
        f.write("</head>\n")
        f.write("<body>\n")

        f.write(f"<h1>Relatório de Escaneamento</h1>\n")
        f.write(f"<div class='info'>\n")
        f.write(f"<p><strong>Data:</strong> {report.timestamp}</p>\n")
        f.write(f"<p><strong>Rede:</strong> {network.ip}</p>\n")
        f.write(f"<p><strong>Dispositivos IoT encontrados:</strong> {len(devices)}</p>\n")
        f.write("</div>\n")

        for device in devices:
            f.write("<div class='device'>\n")
            f.write(f"<p><strong>Hostname:</strong> {device.hostname or 'N/A'}</p>\n")
            f.write(f"<p><strong>IP:</strong> {device.ip}</p>\n")
            f.write(f"<p><strong>MAC:</strong> {device.mac or 'N/A'}</p>\n")
            f.write(f"<p><strong>Portas abertas:</strong> {', '.join(map(str, device.ports)) if device.ports else 'Nenhuma'}</p>\n")
            f.write("</div>\n")

        f.write("</body>\n")
        f.write("</html>\n")
