"""
Vulnerable IoT REST API server.

Vulnerabilities:
  - CORS wildcard (Access-Control-Allow-Origin: *)
  - Debug endpoint exposed (probabilistic — flickers on/off)
  - Default API key (hardcoded)
  - Information disclosure via /api/info
  - No rate limiting on auth endpoint
  - JWT secret leak in error messages
  - Open /metrics endpoint (Prometheus-style)
"""

import json
import random
import time
import os
from http.server import HTTPServer, BaseHTTPRequestHandler

# Probabilistic: debug endpoint available ~70% of the time
# This creates variability across experiment runs
DEBUG_SEED = int(time.time()) % 100
DEBUG_ENABLED = (DEBUG_SEED % 10) < 7  # ~70% chance

API_KEY = "iot-default-key-12345"
JWT_SECRET = "super_secret_jwt_key_do_not_share"


class VulnAPIHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # Silence logs

    def _cors_headers(self):
        """VULN: CORS wildcard allows any origin"""
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")

    def _json_response(self, code, data):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Server", "IoT-API/2.1.3-beta")  # VULN: verbose server header
        self._cors_headers()
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def do_OPTIONS(self):
        """VULN: CORS preflight accepts everything"""
        self.send_response(200)
        self._cors_headers()
        self.end_headers()

    def do_GET(self):
        path = self.path.rstrip("/")

        if path == "" or path == "/":
            self._json_response(200, {
                "service": "IoT Device API",
                "version": "2.1.3-beta",
                "endpoints": ["/api/info", "/api/devices", "/api/auth", "/health"],
            })

        elif path == "/api/info":
            # VULN: information disclosure — exposes internal details
            self._json_response(200, {
                "hostname": "iot-gateway-01",
                "internal_ip": "172.20.0.23",
                "firmware": "2.1.3-beta",
                "uptime_sec": int(time.time()) % 86400,
                "debug_mode": DEBUG_ENABLED,
                "api_key_hint": API_KEY[:8] + "...",
                "db_host": "172.20.0.50:5432",
            })

        elif path == "/api/devices":
            self._json_response(200, {
                "devices": [
                    {"id": "cam-01", "type": "camera", "status": "online"},
                    {"id": "sensor-02", "type": "temperature", "status": "online"},
                    {"id": "lock-03", "type": "smart_lock", "status": "offline"},
                ],
            })

        elif path == "/api/debug" and DEBUG_ENABLED:
            # VULN: debug endpoint exposed (probabilistic)
            self._json_response(200, {
                "debug": True,
                "env": "production",
                "jwt_secret": JWT_SECRET,
                "db_connection": "postgresql://admin:admin@db:5432/iot",
                "log_level": "DEBUG",
                "stack_trace_enabled": True,
            })

        elif path == "/api/debug" and not DEBUG_ENABLED:
            self._json_response(404, {"error": "Not found"})

        elif path == "/metrics":
            # VULN: Prometheus metrics exposed without auth
            metrics_text = (
                "# HELP iot_requests_total Total API requests\n"
                "iot_requests_total{method=\"GET\"} 15234\n"
                "iot_requests_total{method=\"POST\"} 892\n"
                "# HELP iot_auth_failures Authentication failures\n"
                "iot_auth_failures_total 47\n"
                "# HELP iot_memory_bytes Memory usage\n"
                "iot_memory_bytes 67108864\n"
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self._cors_headers()
            self.end_headers()
            self.wfile.write(metrics_text.encode())

        elif path == "/health":
            self._json_response(200, {"status": "healthy", "uptime": int(time.time()) % 86400})

        elif path == "/.env":
            # VULN: environment file accessible
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"API_KEY=iot-default-key-12345\nDB_PASS=admin123\nJWT_SECRET=super_secret_jwt_key_do_not_share\n")

        else:
            self._json_response(404, {"error": "Not found"})

    def do_POST(self):
        path = self.path.rstrip("/")

        if path == "/api/auth":
            content_len = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_len) if content_len > 0 else b""

            try:
                data = json.loads(body) if body else {}
            except json.JSONDecodeError:
                # VULN: JWT secret leaked in error message
                self._json_response(400, {
                    "error": "Invalid JSON",
                    "hint": f"Expected JSON with 'api_key'. Server JWT uses HS256 with key length {len(JWT_SECRET)}",
                })
                return

            if data.get("api_key") == API_KEY:
                self._json_response(200, {"token": "eyJhbGciOiJIUzI1NiJ9.fake_token", "expires": 3600})
            else:
                # VULN: no rate limiting, reveals valid key format
                self._json_response(401, {
                    "error": "Invalid API key",
                    "format": "Key should be 21 characters starting with 'iot-'",
                })
        else:
            self._json_response(404, {"error": "Not found"})


if __name__ == "__main__":
    port = 80
    server = HTTPServer(("0.0.0.0", port), VulnAPIHandler)
    print(f"[HTTP-API] Vulnerable API running on port {port} (debug={'ON' if DEBUG_ENABLED else 'OFF'})")
    server.serve_forever()
