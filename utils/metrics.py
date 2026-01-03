import json
from pathlib import Path
from datetime import datetime

METRICS_FILE = Path("metrics/experiment_metrics.json")

def save_metrics(entry):
    METRICS_FILE.parent.mkdir(exist_ok=True)

    if METRICS_FILE.exists():
        data = json.loads(METRICS_FILE.read_text())
    else:
        data = []

    entry["timestamp"] = datetime.utcnow().isoformat()
    data.append(entry)

    METRICS_FILE.write_text(json.dumps(data, indent=2))
