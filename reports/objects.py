from datetime import datetime

class Device:

    def __init__(self, ip, mac = None, hostname = None, ports = None):
        self.ip = ip
        self.mac = mac
        self.hostname = hostname
        self.ports = ports

class Network:

    def __init__(self, ip, devices):
        self.ip = ip
        self.devices = devices

class Report:

    def __init__(self, ip, devices, output = "report.txt"):
        self.network = Network(ip, devices)
        self.output = output
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")