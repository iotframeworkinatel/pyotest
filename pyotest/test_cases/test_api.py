import pytest
import requests

@pytest.mark.iot_security
def test_insecure_api():
    response = requests.get("iot_device_1/api")
    assert response.status_code == 401, "API acessível sem autenticação!"
