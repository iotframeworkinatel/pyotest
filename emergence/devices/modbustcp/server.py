from pymodbus.server.sync import StartTcpServer
from pymodbus.datastore import ModbusSlaveContext, ModbusServerContext
from pymodbus.datastore import ModbusSequentialDataBlock


def run():
    store = ModbusSlaveContext(
        # Holding registers: 100 addresses, first 3 have data (static tests read 0-2)
        hr=ModbusSequentialDataBlock(0, [123, 456, 789] + [0] * 97),
        # Input registers: non-zero values (adaptive tests discover these)
        ir=ModbusSequentialDataBlock(0, [999, 888, 777] + [0] * 7),
        # Coils: writable, with initial values (adaptive tests discover these)
        co=ModbusSequentialDataBlock(0, [1, 0, 1, 0, 1] + [0] * 5),
        # Discrete inputs: readable values (adaptive tests discover these)
        di=ModbusSequentialDataBlock(0, [1, 1, 0, 0, 1] + [0] * 5),
    )

    context = ModbusServerContext(slaves=store, single=True)

    StartTcpServer(context, address=("0.0.0.0", 502))


if __name__ == "__main__":
    run()
