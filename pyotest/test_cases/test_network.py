import pytest
import nmap

@pytest.mark.iot_security
def test_open_ports():
    scanner = nmap.PortScanner()
    scanner.scan("iot_device_1", "22-10000")
    open_ports = [port for port, status in scanner["iot_device_1"]["tcp"].items() if status["state"] == "open"]
    assert len(open_ports) == 0, f"Dispositivo com portas abertas: {open_ports}"
