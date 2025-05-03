from flask import Flask, request, Response

app = Flask(__name__)

@app.route('/')
def index():
    auth = request.authorization
    if auth and auth.username == 'admin' and auth.password == 'admin':
        return "Welcome to Admin Panel!"
    return Response("Unauthorized", 401, {"WWW-Authenticate": 'Basic realm="Login Required"'})


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=80)
