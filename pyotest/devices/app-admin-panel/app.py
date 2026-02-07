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


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=80)
