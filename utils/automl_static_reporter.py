import subprocess
import json
from pathlib import Path
import time
from statistics import mode


def xml_json_test_reporter(test_dir, report_dir):
    report_dir.mkdir(parents=True, exist_ok=True)

    junit_path = report_dir / "automl_tests.xml"
    json_path = report_dir / "automl_tests.json"

    start = time.time()


    cmd = [
        "pytest",
        str(test_dir),
        "--disable-warnings",
        f"--junitxml={junit_path}"
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    duration = time.time() - start

    summary = {
        "return_code": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "duration_sec": duration
    }

    json_path.write_text(json.dumps(summary, indent=2))

    return summary
