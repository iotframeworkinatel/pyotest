import pandas as pd

from utils.protocol_test_map import PROTOCOL_TESTS
from utils.protocols import guess_protocol

def generate_candidates(iot_devices):
    rows = []

    for d in iot_devices:
        for port in d.ports:
            protocol = guess_protocol(port)

            # pula protocolos sem definição de testes
            if protocol not in PROTOCOL_TESTS:
                continue

            for _, test_id, _, auth_required in PROTOCOL_TESTS[protocol]:
                rows.append({
                    "test_strategy": "automl",
                    "device_type": getattr(d, "device_type", "unknown"),
                    "firmware_version": getattr(d, "os", "unknown"),
                    "open_port": port,
                    "protocol": protocol,
                    "service": protocol,
                    "test_id": test_id,
                    "auth_required": auth_required
                })

    # evita duplicatas
    return pd.DataFrame(rows).drop_duplicates(
        subset=["open_port", "protocol", "test_id"]
    )
