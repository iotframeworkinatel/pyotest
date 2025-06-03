import os
from reports import Report  # Ajuste conforme seu projeto

def report(report: Report):
    network = report.network
    devices = report.network.devices

    # Ensure the final extension is .html
    # base_output = os.path.splitext(report.output)[0]
    filename = f"report/{report.timestamp}_vulnerability_report.html"

    with open(filename, "w", encoding="utf-8") as f:
        f.write("<!DOCTYPE html>\n")
        f.write("<html lang='en'>\n")
        f.write("<head>\n")
        f.write("    <meta charset='UTF-8'>\n")
        f.write("    <title>Scan Report</title>\n")
        f.write("    <style>\n")
        f.write("        body { font-family: Arial, sans-serif; margin: 40px; }\n")
        f.write("        h1 { color: #2c3e50; }\n")
        f.write("        .info { margin-bottom: 20px; }\n")
        f.write("        .device { border: 1px solid #ccc; padding: 15px; border-radius: 6px; margin-bottom: 20px; margin-right: 70%;}\n")
        f.write("        .device p { margin: 5px 0; }\n")
        f.write("        .device ul { margin: 5px 0 10px 20px; }\n")
        f.write("    </style>\n")
        f.write("</head>\n")
        f.write("<body>\n")

        f.write(f"<h1>Scan Report</h1>\n")
        f.write(f"<div class='info'>\n")
        f.write(f"<p><strong>Date:</strong> {report.timestamp}</p>\n")
        f.write(f"<p><strong>Network:</strong> {network.ip}</p>\n")
        f.write(f"<p><strong>Detected IoT Devices:</strong> {len(devices)}</p>\n")
        f.write("</div>\n")

        for device in devices:
            f.write("<div class='device'>\n")
            f.write(f"<p><strong>Hostname:</strong> {device.hostname or 'N/A'}</p>\n")
            f.write(f"<p><strong>IP:</strong> {device.ip}</p>\n")
            f.write(f"<p><strong>MAC:</strong> {device.mac or 'N/A'}</p>\n")
            f.write(f"<p><strong>Open Ports:</strong> {', '.join(map(str, device.ports)) if device.ports else 'None'}</p>\n")
            f.write(f"<p><strong>Is IoT Device:</strong> {'Yes' if device.is_iot else 'No'}</p>\n")

            # Vulnerability report
            if hasattr(device, "vulnerabilities") and device.vulnerabilities:
                f.write("<p><strong>Vulnerabilities:</strong></p>\n")
                f.write("<ul>\n")
                for vuln in device.vulnerabilities:
                    f.write(f"<li>{vuln}</li>\n")
                f.write("</ul>\n")
            else:
                f.write("<p><strong>Vulnerabilities:</strong> Sem vulnerabilidades encontradas</p>\n")

            f.write("</div>\n")

        f.write("</body>\n")
        f.write("</html>\n")
