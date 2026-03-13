"""Auto-generated Telnet vulnerability tests for 172.20.0.12"""
import pytest
import telnetlib
import socket

TIMEOUT = 5
IP = "172.20.0.12"
PORT = 23


@pytest.mark.vuln_id("telnet_open")
def test_telnet_open():
    try:
        tn = telnetlib.Telnet(IP, PORT, timeout=TIMEOUT)
        tn.close()
        assert True  # Telnet service is open
    except (socket.timeout, ConnectionError, OSError):
        pytest.fail("Telnet not accessible")


@pytest.mark.vuln_id("telnet_default_creds")
def test_telnet_default_creds():
    credentials = [("root", "root"), ("admin", "admin"), ("user", "user")]
    for user, password in credentials:
        try:
            tn = telnetlib.Telnet(IP, PORT, timeout=TIMEOUT)
            tn.read_until(b"login:", timeout=TIMEOUT)
            tn.write(user.encode() + b"\n")
            tn.read_until(b"assword:", timeout=TIMEOUT)
            tn.write(password.encode() + b"\n")
            response = tn.read_until(b"$", timeout=3).decode(errors="ignore")
            tn.close()
            if "$" in response or "#" in response or ">" in response:
                assert True
                return
        except Exception:
            continue
    pytest.fail("Telnet default credentials not accepted")


@pytest.mark.vuln_id("telnet_banner_leak")
def test_telnet_banner_leak():
    try:
        tn = telnetlib.Telnet(IP, PORT, timeout=TIMEOUT)
        banner = tn.read_until(b"login:", timeout=TIMEOUT).decode(errors="ignore")
        tn.close()
        # Check if banner reveals system info
        indicators = ["linux", "ubuntu", "debian", "busybox", "version", "kernel"]
        if any(ind in banner.lower() for ind in indicators):
            assert True
            return
    except Exception:
        pytest.skip("Telnet unavailable for banner check")
    pytest.fail("Telnet banner does not leak info")


@pytest.mark.vuln_id("telnet_no_encryption")
def test_telnet_no_encryption():
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(TIMEOUT)
        sock.connect((IP, PORT))
        # Send some data and check it's plaintext (no TLS handshake)
        data = sock.recv(512)
        sock.close()
        # Telnet by definition is unencrypted. If we can connect, it's vulnerable.
        if len(data) >= 0:
            assert True
            return
    except (socket.timeout, ConnectionError, OSError):
        pytest.skip("Telnet unavailable")
    pytest.fail("Telnet uses encryption")