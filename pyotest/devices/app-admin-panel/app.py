from flask import Flask, request, Response

app = Flask(__name__)


@app.route('/')
def index():
    auth = request.authorization
    if auth and auth.username == 'admin' and auth.password == 'admin':
        return "Welcome to Admin Panel!"
    return Response("Unauthorized", 401, {"WWW-Authenticate": 'Basic realm="Login Required"'})


# Exposed admin interface: triggers http_open_admin test
@app.route('/admin')
def admin():
    return "<html><body><h1>Admin Dashboard</h1><p>Device management</p></body></html>"


@app.route('/login')
def login():
    return "<html><body><h1>Login</h1><form><input name='user'/><input name='pass'/></form></body></html>"


# Sensitive file exposure: triggers http_sensitive_files test
@app.route('/config.php')
def config_file():
    return "<?php $db_host='localhost'; $db_user='root'; $db_pass='admin123'; ?>"


# --- HIDDEN VULNERABILITIES (only adaptive tests will discover these) ---

# SQL injection endpoint — input reflected without sanitization
@app.route('/api/search')
def api_search():
    query = request.args.get('q', '')
    return f'{{"results": [], "query": "{query}"}}'


# Debug endpoint — not in static open_admin paths ["/admin", "/login", "/dashboard"]
@app.route('/api/debug')
def api_debug():
    return '{"debug": true, "env": "production", "db": "sqlite:///app.db"}'


# Backup config — not in static sensitive_files list
@app.route('/.env.bak')
def env_backup():
    return "DB_PASSWORD=admin123\nSECRET=old_secret_key"


# Robots.txt revealing hidden paths
@app.route('/robots.txt')
def robots():
    return "User-agent: *\nDisallow: /api/debug\nDisallow: /api/v2\nDisallow: /backup/"


# CORS misconfiguration — permissive headers on all responses
@app.after_request
def add_cors(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Credentials'] = 'true'
    return response


# Cookie without HttpOnly/Secure flags
@app.route('/api/session')
def api_session():
    resp = Response('{"session": "active"}')
    resp.set_cookie('session_id', 'abc123', httponly=False, secure=False, samesite=None)
    return resp


# Additional weak credential pair — user/1234 (not in static COMMON_CREDENTIALS)
@app.route('/api/v2')
def api_v2():
    auth = request.authorization
    if auth and auth.username == 'user' and auth.password == '1234':
        return '{"status": "authenticated", "role": "admin"}'
    return Response("Unauthorized", 401, {"WWW-Authenticate": 'Basic realm="API v2"'})


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=80)
