def generate_candidates(iot_devices):
    rows = []

    for d in iot_devices:
        for port in d.ports:
            rows.append({
                "test_strategy": "automl",
                "device_type": getattr(d, "type", "unknown"),
                "firmware_version": getattr(d, "firmware", "unknown"),
                "open_port": port,
                "protocol": guess_protocol(port),
                "service": guess_protocol(port),
                "auth_required": port in [21, 22, 23, 80, 1883]
            })

    return rows



def guess_protocol(port):
    return {
        21: "ftp",
        22: "ssh",
        23: "telnet",
        80: "http",
        1883: "mqtt",
        554: "rtsp"
    }.get(port, "generic")
