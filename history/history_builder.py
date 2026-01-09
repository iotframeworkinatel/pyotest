import csv
import uuid
from datetime import datetime
from pathlib import Path

class HistoryBuilder:
    COLUMNS = [
        "experiment_id",
        "timestamp",
        "test_strategy",
        "container_id",
        "device_type",
        "firmware_version",
        "open_port",
        "protocol",
        "service",
        "auth_required",
        "test_id",
        "test_type",
        "payload_size",
        "timeout",
        "vulnerability_found",
        "execution_time_ms"
    ]

    def __init__(self, path):
        self.path = Path(path)
        self._init_file()

    def _init_file(self):
        if not self.path.exists():
            with open(self.path, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=self.COLUMNS)
                writer.writeheader()

    def log(self, data: dict):
        data = data.copy()
        data["experiment_id"] = data.get(
            "experiment_id", str(uuid.uuid4())
        )
        data["timestamp"] = datetime.utcnow().isoformat()

        with open(self.path, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=self.COLUMNS)
            writer.writerow(data)
