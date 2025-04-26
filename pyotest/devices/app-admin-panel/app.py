from flask import Flask, request

app = Flask(__name__)

@app.route('/')
def index():
    auth = request.authorization
    if auth and auth.username == 'admin' and auth.password == 'admin':
        return "Welcome to Admin Panel!"
    return "Unauthorized", 401

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=80)
