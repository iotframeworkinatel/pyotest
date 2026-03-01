import uuid
from pathlib import Path
from datetime import datetime

class ExperimentManager:
    def __init__(self, base_dir="experiments"):
        timestamp = datetime.utcnow().strftime("%Y-%m-%d_%H-%M-%S")
        # Add a short random suffix to guarantee uniqueness even for rapid-fire runs
        suffix = uuid.uuid4().hex[:6]
        self.root = Path(base_dir) / f"exp_{timestamp}_{suffix}"
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, filename):
        return self.root / filename
