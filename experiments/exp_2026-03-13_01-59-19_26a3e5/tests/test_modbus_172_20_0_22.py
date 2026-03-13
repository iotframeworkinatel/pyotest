"""Auto-generated Modbus TCP vulnerability tests for 172.20.0.22"""
import pytest
from pymodbus.client.sync import ModbusTcpClient

TIMEOUT = 5

@pytest.mark.vuln_id("MODBUS_READ_REGISTER")
def test_modbus_read_register():
    ip = "172.20.0.22"
    port = 502
    client = ModbusTcpClient(ip, port=port, timeout=TIMEOUT)

    try:
        if client.connect():
            result = client.read_holding_registers(0, 3, unit=1)
            if not result.isError():
                assert True  # Registers readable without auth
                return
    except Exception:
        pass
    finally:
        client.close()

    pytest.fail("Modbus holding registers not readable")


@pytest.mark.vuln_id("MODBUS_DEVICE_ID")
def test_modbus_device_id():
    ip = "172.20.0.22"
    port = 502
    client = ModbusTcpClient(ip, port=port, timeout=TIMEOUT)

    try:
        if client.connect():
            result = client.read_device_information()
            if result and not result.isError():
                assert True  # Device ID exposed
                return
    except Exception:
        pass
    finally:
        client.close()

    pytest.fail("Modbus device ID not accessible")


@pytest.mark.vuln_id("MODBUS_WRITE_COIL")
def test_modbus_write_coil():
    ip = "172.20.0.22"
    port = 502
    client = ModbusTcpClient(ip, port=port, timeout=TIMEOUT)

    try:
        if client.connect():
            # Read current coil value first
            read_result = client.read_coils(0, 1, unit=1)
            if not read_result.isError():
                # Attempt write
                write_result = client.write_coil(0, True, unit=1)
                if not write_result.isError():
                    assert True  # Coil writable without auth
                    return
    except Exception:
        pass
    finally:
        client.close()

    pytest.fail("Modbus coils not writable")


@pytest.mark.vuln_id("MODBUS_READ_INPUT_REG")
def test_modbus_read_input_reg():
    ip = "172.20.0.22"
    port = 502
    client = ModbusTcpClient(ip, port=port, timeout=TIMEOUT)

    try:
        if client.connect():
            result = client.read_input_registers(0, 3, unit=1)
            if not result.isError():
                assert True
                return
    except Exception:
        pass
    finally:
        client.close()

    pytest.fail("Modbus input registers not readable")


@pytest.mark.vuln_id("MODBUS_WRITE_REGISTER")
def test_modbus_write_register():
    ip = "172.20.0.22"
    port = 502
    client = ModbusTcpClient(ip, port=port, timeout=TIMEOUT)

    try:
        if client.connect():
            result = client.write_register(0, 999, unit=1)
            if not result.isError():
                assert True
                return
    except Exception:
        pass
    finally:
        client.close()

    pytest.fail("Modbus holding registers not writable")


@pytest.mark.vuln_id("MODBUS_READ_DISCRETE")
def test_modbus_read_discrete():
    ip = "172.20.0.22"
    port = 502
    client = ModbusTcpClient(ip, port=port, timeout=TIMEOUT)

    try:
        if client.connect():
            result = client.read_discrete_inputs(0, 5, unit=1)
            if not result.isError():
                assert True
                return
    except Exception:
        pass
    finally:
        client.close()

    pytest.fail("Modbus discrete inputs not readable")


@pytest.mark.vuln_id("MODBUS_READ_COILS")
def test_modbus_read_coils():
    ip = "172.20.0.22"
    port = 502
    client = ModbusTcpClient(ip, port=port, timeout=TIMEOUT)

    try:
        if client.connect():
            result = client.read_coils(0, 5, unit=1)
            if not result.isError():
                assert True
                return
    except Exception:
        pass
    finally:
        client.close()

    pytest.fail("Modbus coils not readable")