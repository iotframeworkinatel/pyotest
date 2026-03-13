"""Auto-generated HTTP vulnerability tests for 172.20.0.23"""
import pytest
import requests

TIMEOUT = 5
IP = "172.20.0.23"
PORTS = "80".split(",")

WEAK_CREDENTIALS = [
    ("admin", "admin"),
    ("root", "root"),
    ("user", "user"),
    ("test", "test"),
    ("admin", "1234"),
    ("admin", "password"),
    ("operator", "operator"),
]

SENSITIVE_PATHS = ["/.env", "/config.php", "/wp-config.php", "/.git/config"]
SENSITIVE_PATHS_EXT = ["/.env.bak", "/robots.txt", "/api/debug", "/server-status", "/.DS_Store"]
ADMIN_PATHS = ["/admin", "/dashboard", "/manage", "/admin.php"]
ADMIN_PATHS_EXT = ["/api/v1", "/api/v2", "/management", "/console", "/actuator"]
TRAVERSAL_PAYLOADS = ["../../../etc/passwd", "..\\..\\..\\etc\\passwd"]
TRAVERSAL_ENCODED = ["%2e%2e%2f%2e%2e%2f%2e%2e%2fetc/passwd", "..%252f..%252f..%252fetc/passwd", "..%00/etc/passwd"]
SQLI_PAYLOADS = ["' OR '1'='1", "1; DROP TABLE", "' UNION SELECT NULL--"]


def _url(port):
    return f"http://{IP}:{port}"


@pytest.mark.vuln_id("http_default_credentials")
def test_http_default_credentials():
    for port in PORTS:
        try:
            r = requests.get(_url(port), auth=("admin", "admin"), timeout=TIMEOUT)
            if r.status_code < 400:
                assert True
                return
        except requests.RequestException:
            continue
    pytest.fail("HTTP default credentials not accepted")


@pytest.mark.vuln_id("http_directory_listing")
def test_http_directory_listing():
    for port in PORTS:
        try:
            r = requests.get(_url(port), timeout=TIMEOUT)
            if r.status_code == 200:
                body = r.text.lower()
                if "index of" in body or "directory listing" in body or "<pre>" in body:
                    assert True
                    return
        except requests.RequestException:
            continue
    pytest.fail("No directory listing found")


@pytest.mark.vuln_id("http_directory_traversal")
def test_http_directory_traversal():
    for port in PORTS:
        for payload in TRAVERSAL_PAYLOADS:
            try:
                r = requests.get(f"{_url(port)}/{payload}", timeout=TIMEOUT)
                if r.status_code == 200 and ("root:" in r.text or "daemon:" in r.text):
                    assert True
                    return
            except requests.RequestException:
                continue
    pytest.fail("Path traversal not exploitable")


@pytest.mark.vuln_id("http_dangerous_methods")
def test_http_dangerous_methods():
    for port in PORTS:
        try:
            r = requests.options(_url(port), timeout=TIMEOUT)
            allow = r.headers.get("Allow", "").upper()
            if any(m in allow for m in ["PUT", "DELETE", "TRACE"]):
                assert True
                return
        except requests.RequestException:
            continue
    pytest.fail("No dangerous HTTP methods enabled")


@pytest.mark.vuln_id("http_missing_sec_headers")
def test_http_missing_sec_headers():
    security_headers = [
        "X-Frame-Options",
        "X-Content-Type-Options",
        "Content-Security-Policy",
        "Strict-Transport-Security",
    ]
    for port in PORTS:
        try:
            r = requests.get(_url(port), timeout=TIMEOUT)
            missing = [h for h in security_headers if h.lower() not in {k.lower() for k in r.headers}]
            if len(missing) >= 2:
                assert True
                return
        except requests.RequestException:
            continue
    pytest.fail("Security headers are present")


@pytest.mark.vuln_id("http_sensitive_files")
def test_http_sensitive_files():
    for port in PORTS:
        for path in SENSITIVE_PATHS:
            try:
                r = requests.get(f"{_url(port)}{path}", timeout=TIMEOUT)
                if r.status_code == 200 and len(r.text.strip()) > 10:
                    assert True
                    return
            except requests.RequestException:
                continue
    pytest.fail("No sensitive files exposed")


@pytest.mark.vuln_id("http_open_admin")
def test_http_open_admin():
    for port in PORTS:
        for path in ADMIN_PATHS:
            try:
                r = requests.get(f"{_url(port)}{path}", timeout=TIMEOUT, allow_redirects=False)
                if r.status_code in (200, 301, 302):
                    assert True
                    return
            except requests.RequestException:
                continue
    pytest.fail("No admin panel found")


@pytest.mark.vuln_id("http_verbose_server")
def test_http_verbose_server():
    for port in PORTS:
        try:
            r = requests.get(_url(port), timeout=TIMEOUT)
            server = r.headers.get("Server", "")
            if server and ("/" in server or any(c.isdigit() for c in server)):
                assert True
                return
        except requests.RequestException:
            continue
    pytest.fail("Server header not verbose")


@pytest.mark.vuln_id("http_no_auth")
def test_http_no_auth():
    for port in PORTS:
        try:
            r = requests.get(_url(port), timeout=TIMEOUT)
            if r.status_code == 200 and len(r.text) > 50:
                assert True
                return
        except requests.RequestException:
            continue
    pytest.fail("HTTP requires authentication")


@pytest.mark.vuln_id("http_sensitive_files_ext")
def test_http_sensitive_files_ext():
    for port in PORTS:
        for path in SENSITIVE_PATHS_EXT:
            try:
                r = requests.get(f"{_url(port)}{path}", timeout=TIMEOUT)
                if r.status_code == 200 and len(r.text.strip()) > 10:
                    assert True
                    return
            except requests.RequestException:
                continue
    pytest.fail("No extended sensitive files exposed")


@pytest.mark.vuln_id("http_open_admin_ext")
def test_http_open_admin_ext():
    for port in PORTS:
        for path in ADMIN_PATHS_EXT:
            try:
                r = requests.get(f"{_url(port)}{path}", timeout=TIMEOUT, allow_redirects=False)
                if r.status_code in (200, 301, 302):
                    assert True
                    return
            except requests.RequestException:
                continue
    pytest.fail("No extended admin endpoints found")


@pytest.mark.vuln_id("http_cors_misconfig")
def test_http_cors_misconfig():
    for port in PORTS:
        try:
            r = requests.get(
                _url(port),
                headers={"Origin": "https://evil.com"},
                timeout=TIMEOUT,
            )
            acao = r.headers.get("Access-Control-Allow-Origin", "")
            if acao == "*" or "evil.com" in acao:
                assert True
                return
        except requests.RequestException:
            continue
    pytest.fail("CORS properly configured")


@pytest.mark.vuln_id("http_insecure_cookies")
def test_http_insecure_cookies():
    for port in PORTS:
        try:
            r = requests.get(_url(port), timeout=TIMEOUT)
            for cookie_header in r.headers.get("Set-Cookie", "").split(","):
                cl = cookie_header.lower()
                if cl and ("secure" not in cl or "httponly" not in cl):
                    assert True
                    return
        except requests.RequestException:
            continue
    pytest.fail("Cookies are secure")


@pytest.mark.vuln_id("http_trace_method")
def test_http_trace_method():
    for port in PORTS:
        try:
            r = requests.request("TRACE", _url(port), timeout=TIMEOUT)
            if r.status_code == 200 and "trace" in r.text.lower():
                assert True
                return
        except requests.RequestException:
            continue
    pytest.fail("TRACE method not enabled")


@pytest.mark.vuln_id("http_default_creds_ext")
def test_http_default_creds_ext():
    for port in PORTS:
        for user, passwd in WEAK_CREDENTIALS:
            try:
                r = requests.get(_url(port), auth=(user, passwd), timeout=TIMEOUT)
                if r.status_code < 400:
                    assert True
                    return
            except requests.RequestException:
                continue
    pytest.fail("Extended credentials not accepted")


@pytest.mark.vuln_id("http_traversal_encoded")
def test_http_traversal_encoded():
    for port in PORTS:
        for payload in TRAVERSAL_ENCODED:
            try:
                r = requests.get(f"{_url(port)}/{payload}", timeout=TIMEOUT, allow_redirects=False)
                if r.status_code == 200 and ("root:" in r.text or "daemon:" in r.text):
                    assert True
                    return
            except requests.RequestException:
                continue
    pytest.fail("Encoded path traversal not exploitable")


@pytest.mark.vuln_id("http_sqli_probe")
def test_http_sqli_probe():
    for port in PORTS:
        for payload in SQLI_PAYLOADS:
            try:
                r = requests.get(f"{_url(port)}/?id={payload}", timeout=TIMEOUT)
                body = r.text.lower()
                if any(kw in body for kw in ["sql", "syntax", "mysql", "sqlite", "postgresql", "oracle"]):
                    assert True
                    return
            except requests.RequestException:
                continue
    pytest.fail("No SQL injection detected")