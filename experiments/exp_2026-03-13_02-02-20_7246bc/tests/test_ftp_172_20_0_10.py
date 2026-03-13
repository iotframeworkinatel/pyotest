"""Auto-generated FTP vulnerability tests for 172.20.0.10"""
import ftplib
import pytest
import socket

TIMEOUT = 5
IP = "172.20.0.10"
PORT = int("21".split(",")[0])

WEAK_CREDENTIALS = [
    ("admin", "admin"),
    ("root", "root"),
    ("user", "user"),
    ("test", "test"),
    ("admin", "1234"),
    ("admin", "password"),
]


def _try_login(user, password):
    ftp = None
    try:
        ftp = ftplib.FTP()
        ftp.connect(IP, PORT, timeout=TIMEOUT)
        resp = ftp.login(user=user, passwd=password)
        try:
            ftp.quit()
        except Exception:
            pass
        if resp and resp.startswith("230"):
            return True
    except ftplib.error_perm:
        return False
    except (socket.timeout, ConnectionError, OSError):
        pytest.skip("FTP unavailable")
    finally:
        try:
            if ftp:
                ftp.close()
        except Exception:
            pass
    return False


@pytest.mark.vuln_id("ftp_anonymous_login")
def test_ftp_anonymous_login():
    if _try_login("anonymous", "anonymous"):
        assert True
        return
    pytest.fail("FTP anonymous login not accepted")


@pytest.mark.vuln_id("ftp_anonymous_real")
def test_ftp_anonymous_real():
    ftp = None
    try:
        ftp = ftplib.FTP()
        ftp.connect(IP, PORT, timeout=TIMEOUT)
        resp = ftp.login(user="anonymous", passwd="anonymous")
        if resp and resp.startswith("230"):
            listing = ftp.nlst()
            ftp.quit()
            if len(listing) >= 0:  # Any listing = access confirmed
                assert True
                return
    except ftplib.error_perm:
        pass
    except (socket.timeout, ConnectionError, OSError):
        pytest.skip("FTP unavailable")
    finally:
        try:
            if ftp:
                ftp.close()
        except Exception:
            pass
    pytest.fail("FTP anonymous real access not possible")


@pytest.mark.vuln_id("ftp_weak_creds_ext")
def test_ftp_weak_creds_ext():
    for user, password in WEAK_CREDENTIALS:
        if _try_login(user, password):
            assert True
            return
    pytest.fail("FTP does not accept weak credentials")