from pymodbus.server.sync import StartTcpServer
from pymodbus.datastore import ModbusSlaveContext, ModbusServerContext
from pymodbus.datastore import ModbusSequentialDataBlock


def run():
    store = ModbusSlaveContext(
        hr=ModbusSequentialDataBlock(0, [123, 456, 789]),
        ir=ModbusSequentialDataBlock(0, [0] * 10),
        co=ModbusSequentialDataBlock(0, [0] * 10),
        di=ModbusSequentialDataBlock(0, [0] * 10),
    )

    context = ModbusServerContext(slaves=store, single=True)

    StartTcpServer(context, address=("0.0.0.0", 502))


if __name__ == "__main__":
    run()
