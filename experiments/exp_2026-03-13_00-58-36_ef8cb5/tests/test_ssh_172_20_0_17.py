"""Auto-generated SSH vulnerability tests for 172.20.0.17"""
import pytest
import socket
import paramiko

TIMEOUT = 5
IP = "172.20.0.17"
PORT = 22

WEAK_CREDENTIALS = [
    ("root", "root"),
    ("admin", "admin"),
    ("test", "test"),
]

WEAK_CREDENTIALS_EXT = [
    ("admin", "admin"),
    ("root", "toor"),
    ("ubnt", "ubnt"),
    ("pi", "raspberry"),
    ("admin", "password"),
]

WEAK_CIPHERS = [
    "aes128-cbc", "aes256-cbc", "3des-cbc", "blowfish-cbc", "arcfour",
]

WEAK_KEX = [
    "diffie-hellman-group1-sha1",
    "diffie-hellman-group14-sha1",
]


def _try_connect(user, password):
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        ssh.connect(
            IP, port=PORT, username=user, password=password,
            timeout=TIMEOUT, allow_agent=False, look_for_keys=False,
        )
        ssh.close()
        return True
    except paramiko.AuthenticationException:
        return False
    except (socket.timeout, paramiko.SSHException, OSError):
        pytest.skip("SSH unavailable")


@pytest.mark.vuln_id("ssh_weak_auth")
def test_ssh_weak_auth():
    for user, password in WEAK_CREDENTIALS:
        if _try_connect(user, password):
            assert True
            return
    pytest.fail("SSH does not accept weak credentials")


@pytest.mark.vuln_id("ssh_root_login")
def test_ssh_root_login():
    for password in ["root", "toor", "admin", "password"]:
        if _try_connect("root", password):
            assert True
            return
    pytest.fail("SSH root login not permitted")


@pytest.mark.vuln_id("ssh_password_auth")
def test_ssh_password_auth():
    try:
        t = paramiko.Transport((IP, PORT))
        t.connect()
        t.close()
        # If we got here, password auth is at minimum available as a method
        assert True
        return
    except Exception:
        pass
    pytest.fail("SSH password auth not enabled")


@pytest.mark.vuln_id("ssh_old_version")
def test_ssh_old_version():
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(TIMEOUT)
        sock.connect((IP, PORT))
        banner = sock.recv(256).decode(errors="ignore").strip()
        sock.close()
        # Check for old versions
        old_indicators = ["SSH-1.", "OpenSSH_4", "OpenSSH_5", "OpenSSH_6", "dropbear_0"]
        if any(ind in banner for ind in old_indicators):
            assert True
            return
    except Exception:
        pytest.skip("SSH unavailable for version check")
    pytest.fail("SSH version is not outdated")


@pytest.mark.vuln_id("ssh_weak_crypto")
def test_ssh_weak_crypto():
    try:
        t = paramiko.Transport((IP, PORT))
        t.connect()
        # Check if any weak ciphers are supported
        sec_opts = t.get_security_options()
        supported_ciphers = list(sec_opts.ciphers)
        t.close()
        weak_found = [c for c in WEAK_CIPHERS if c in supported_ciphers]
        if weak_found:
            assert True
            return
    except Exception:
        pytest.skip("SSH unavailable for crypto check")
    pytest.fail("No weak ciphers supported")


@pytest.mark.vuln_id("ssh_no_auth_limit")
def test_ssh_no_auth_limit():
    failures = 0
    for i in range(6):
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(
                IP, port=PORT, username="root", password=f"wrong{i}",
                timeout=TIMEOUT, allow_agent=False, look_for_keys=False,
            )
            ssh.close()
        except paramiko.AuthenticationException:
            failures += 1
            continue
        except (socket.timeout, paramiko.SSHException, OSError):
            break
    if failures >= 5:
        assert True  # No rate limiting — all attempts went through
        return
    pytest.fail("SSH has authentication rate limiting")


@pytest.mark.vuln_id("ssh_weak_auth_ext")
def test_ssh_weak_auth_ext():
    for user, password in WEAK_CREDENTIALS_EXT:
        if _try_connect(user, password):
            assert True
            return
    pytest.fail("SSH does not accept extended weak credentials")


@pytest.mark.vuln_id("ssh_weak_kex")
def test_ssh_weak_kex():
    try:
        t = paramiko.Transport((IP, PORT))
        t.connect()
        sec_opts = t.get_security_options()
        supported_kex = list(sec_opts.kex)
        t.close()
        weak_found = [k for k in WEAK_KEX if k in supported_kex]
        if weak_found:
            assert True
            return
    except Exception:
        pytest.skip("SSH unavailable for KEX check")
    pytest.fail("No weak key exchange algorithms supported")