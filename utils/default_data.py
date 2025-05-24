COMMON_VULN_PORTS = {
    21: "FTP",
    22: "SSH",
    23: "Telnet",
    80: "HTTP",
    443: "HTTPS",
    554: "RTSP",
    1883: "MQTT",
    8883: "MQTT sobre TLS",
    8080: "HTTP alternativa",
    2323: "Telnet alternativa",
    5678: "UDP Discovery (MikroTik, Sonoff, etc)",
    6668: "Tuya Smart",
    9999: "TP-Link Smart Home",
    50000: "iiimsf"
}

COMMON_CREDENTIALS = [
    ('root', 'root'),
    ('admin', 'admin'),
]

# COMMON_CREDENTIALS = [
#     ('root', 'root'),
#     ('root', 'admin'),
#     ('root', 'password'),
#     ('root', '12345'),
#     ('admin', 'admin'),
#     ('admin', 'password'),
#     ('admin', ''),
#     ('user', 'user'),
#     ('test', 'test'),
# ]