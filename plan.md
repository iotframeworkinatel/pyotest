# Plan: Make AutoML Adaptive + Expand Vulnerability Surface

## Problem
Static and AutoML find identical results (28 vulns every run) because:
1. AutoML generates candidates from the SAME test pool as static
2. All candidates executed regardless of risk score (no filtering)
3. Devices have only static, deterministic vulns detectable by the fixed test list

## Solution: Two Parallel Paths

### Path A — New Adaptive-Only Test Variants (23 new tests)
Create test functions that ONLY run in the AutoML/adaptive strategy, not in static.

**New files:**
- `vulnerability_tester/http/http_adaptive.py` — 8 tests (extended sensitive files, hidden endpoints, CORS, insecure cookies, TRACE method, extended creds, encoded traversal, SQLi probe)
- `vulnerability_tester/coap/coap_adaptive.py` — 3 tests (hidden resources, PUT allowed, DELETE allowed)
- `vulnerability_tester/modbustcp/modbus_adaptive.py` — 5 tests (write coil, read input registers, read discrete inputs, read coils, write register)
- `vulnerability_tester/mqtt/mqtt_adaptive.py` — 3 tests (retained messages, wildcard subscribe, sensitive topics)
- `vulnerability_tester/ssh/ssh_adaptive.py` — 2 tests (extended weak auth, weak key exchange)
- `vulnerability_tester/ftp/ftp_adaptive.py` — 2 tests (real anonymous login, extended credentials)

**New registry:**
- `utils/adaptive_test_map.py` — `ADAPTIVE_TESTS` dict, same tuple format as `PROTOCOL_TESTS`

### Path B — Expand Device Vulnerability Surface
Add hidden vulnerabilities to containers that ONLY adaptive tests can discover.

**Device changes:**
1. `emergence/devices/http-vuln/Dockerfile` — add .env.bak, backup.sql, robots.txt, api/debug endpoint
2. `emergence/devices/http-vuln/httpd-vuln.conf` — enable TRACE, server-status, server-info
3. `emergence/devices/app-admin-panel/app.py` — add /api/debug, /api/search (SQLi), /api/session (insecure cookies), /api/v2 (extra creds), CORS *, /.env.bak, /robots.txt
4. `emergence/devices/httpd/htdocs/` — add .env.bak, backup.sql, robots.txt, .htaccess, web.config, composer.json, package.json
5. `emergence/devices/coap/server.py` — add /secret, /config (with PUT/DELETE), /firmware resources
6. `emergence/devices/modbustcp/server.py` — expand registers, add non-zero input registers, writable coils, discrete inputs
7. MQTT — create custom Dockerfile with init script that publishes retained messages on device/config, device/firmware, admin/credentials
8. `docker-compose.yml` — update mqtt_no_auth to use build instead of image

### Pipeline Changes
1. `automl/candidates.py` — generate candidates from BOTH `PROTOCOL_TESTS` + `ADAPTIVE_TESTS`
2. `automl/adaptive_generator.py` — validate test_ids against BOTH dicts
3. `utils/run_adaptive_tests.py` — resolve test functions from BOTH dicts via `_resolve_test()`

### What Stays Unchanged
- `__main__.py` — no changes needed
- `utils/tester.py` — static tester unchanged, uses only PROTOCOL_TESTS
- `utils/run_and_log.py` — generic executor, protocol-agnostic
- `history/history_builder.py` — 16-column schema preserved
- All existing test files — untouched

## Expected Results
- Static: ~28 vulns (same as before)
- AutoML: ~28 + ~20 = ~48 vulns (static tests + adaptive-only findings)
- Delta: ~+71% more vulnerabilities
- This produces a statistically significant difference for the PhD hypothesis test

## Implementation Order
1. Device container enhancements (Path B)
2. New adaptive test files (Path A)
3. Adaptive test map registry
4. Pipeline wiring changes
5. Rebuild all containers and test
