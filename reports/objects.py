from datetime import datetime
from utils.protocols import PORT_PROTOCOL_MAP


class Device:

    def __init__(self, ip, mac=None, hostname=None, ports=None, is_iot=False, vulnerabilities=None, os=None, device_type=None):
        self.ip = ip
        self.mac = mac
        self.hostname = hostname
        self.ports = ports or []
        self.is_iot = is_iot
        self.vulnerabilities = vulnerabilities if vulnerabilities is not None else []
        self.os = os
        self.device_type = device_type

    @property
    def protocols(self) -> list[str]:
        protos = set()
        for port in self.ports:
            proto = PORT_PROTOCOL_MAP.get(int(port))
            if proto:
                protos.add(proto)
        return sorted(protos)

    def to_dict(self) -> dict:
        return {
            "ip": self.ip, "mac": self.mac, "hostname": self.hostname,
            "ports": self.ports, "is_iot": self.is_iot,
            "vulnerabilities": self.vulnerabilities, "os": self.os,
            "device_type": self.device_type, "protocols": self.protocols,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Device":
        return cls(
            ip=data.get("ip", ""), mac=data.get("mac"),
            hostname=data.get("hostname"), ports=data.get("ports", []),
            is_iot=data.get("is_iot", False),
            vulnerabilities=data.get("vulnerabilities", []),
            os=data.get("os"), device_type=data.get("device_type"),
        )

class Network:

    def __init__(self, ip, devices):
        self.ip = ip
        self.devices = devices

class Report:

    def __init__(self, ip, devices, output = "html"):
        self.network = Network(ip, devices)
        self.output = output
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    def set_output(self, output):
        self.output = output