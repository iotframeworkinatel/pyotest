import pytest

@pytest.mark.iot_security
def test_default_password(device):
    assert not device.authenticate("admin", "admin"), "Dispositivo vulnerável a credenciais padrão!"
