from datetime import datetime

class Device:

    def __init__(self, ip, mac = None, hostname = None, ports = None, is_iot = False, vulnerabilities = None):
        self.ip = ip
        self.mac = mac
        self.hostname = hostname
        self.ports = ports
        self.is_iot = is_iot
        self.vulnerabilities = vulnerabilities if vulnerabilities is not None else []

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