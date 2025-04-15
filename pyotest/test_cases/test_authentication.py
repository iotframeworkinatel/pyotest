import pytest, requests

@pytest.mark.iot_security
def test_default_password():
    url = "http://iot_device_1:5000/login"
    credentials = {
        "username": "admin",
        "password": "admin"
    }
    response = requests.post(url, json=credentials)
    assert response.status_code != 200, "Dispositivo vulnerável a credenciais padrão!"
