import h2o
from h2o.automl import H2OAutoML
from pathlib import Path
import json
import time

from utils.automl_tester import xml_json_test_reporter
from utils.junit_to_tests import parse_junit_tests
from jinja2 import Environment, FileSystemLoader

# =========================
# Config
# =========================

HISTORY_FILE = Path("automl_history/history.json")
REPORT_DIR = Path("automl_report")
REPORT_XML = REPORT_DIR / "automl_tests.xml"
GENERATED_TESTS_DIR = Path("generated_tests")

MIN_HISTORY_ROWS = 20
TARGET_COL = "test_useful"
FEATURE_COLS = ["host", "test_type"]

env = Environment(loader=FileSystemLoader("templates"))

GENERATED_TESTS_DIR.mkdir(exist_ok=True)
REPORT_DIR.mkdir(exist_ok=True)

# =========================
# Histórico
# =========================

def load_history():
    if HISTORY_FILE.exists():
        return json.loads(HISTORY_FILE.read_text())
    return []


def save_history(entry):
    HISTORY_FILE.parent.mkdir(exist_ok=True)
    history = load_history()
    history.append(entry)
    HISTORY_FILE.write_text(json.dumps(history, indent=2))


# =========================
# AutoML
# =========================

def train_model(rows):
    frame = h2o.H2OFrame(
        rows,
        column_names=["host", "test_type", "test_useful"]
    )

    frame["host"] = frame["host"].asfactor()
    frame["test_type"] = frame["test_type"].asfactor()
    frame["test_useful"] = frame["test_useful"].asfactor()

    aml = H2OAutoML(
        max_models=10,
        max_runtime_secs=30,
        seed=1
    )

    aml.train(y="test_useful", training_frame=frame)
    return aml.leader


def should_generate_test(model, host, test_type):
    if model is None:
        return True  # bootstrap

    frame = h2o.H2OFrame(
        [{"host": host, "test_type": test_type}],
        column_names=["host", "test_type"]
    )

    frame["host"] = frame["host"].asfactor()
    frame["test_type"] = frame["test_type"].asfactor()

    pred = model.predict(frame).as_data_frame()
    return int(pred.iloc[0, 0]) == 1


# =========================
# Template selection
# =========================

def select_template(test_type):
    t = test_type.lower()

    if "ftp" in t:
        return "ftp_test.py.j2"
    if "ssh" in t:
        return "ssh_test.py.j2"
    if "telnet" in t:
        return "telnet_test.py.j2"
    if "mqtt" in t:
        return "mqtt_test.py.j2"
    if "http" in t or "directory" in t:
        return "http_test.py.j2"

    return "generic_test.py.j2"


# =========================
# Entry point
# =========================

def generate_tests(iot_devices, args):

    start = time.time()

    try:
        h2o.init()
    except Exception as e:
        print("[AML] H2O indisponível:", e)
        return

    history = load_history()

    rows = [
        {
            "host": h["host"],
            "test_type": h["test_type"],
            "test_useful": h["test_useful"]
        }
        for h in history
    ]

    print(f"[AML][DEBUG] Histórico: {len(rows)} linhas")

    model = None
    labels = {r["test_useful"] for r in rows}

    if len(rows) >= MIN_HISTORY_ROWS and len(labels) > 1:
        try:
            model = train_model(rows)
            print("[AML] Modelo AutoML treinado com sucesso")
        except Exception as e:
            print("[AML] AutoML falhou, fallback:", e)

    # -------------------------
    # Geração de testes
    # -------------------------

    generated = []

    for dev in iot_devices:
        host = dev.ip

        for vuln in dev.vulnerabilities:
            test_type = vuln.upper()

            if not should_generate_test(model, host, test_type):
                continue

            template = env.get_template(select_template(test_type))

            filename = f"test_{host}_{test_type}".lower().replace(".", "_")
            path = GENERATED_TESTS_DIR / f"{filename}.py"

            path.write_text(template.render(
                ip=dev.ip,
                hostname=getattr(dev, "hostname", ""),
                ports=",".join(map(str, dev.ports)),
                test_type=test_type
            ))

            generated.append(path)

    print(f"[AML] {len(generated)} testes gerados")

    if not generated:
        print("[AML] Nenhum teste gerado")
        return

    # -------------------------
    # Executa pytest
    # -------------------------

    xml_json_test_reporter(
        test_dir=GENERATED_TESTS_DIR,
        report_dir=REPORT_DIR
    )

    # -------------------------
    # Feedback supervisionado
    # -------------------------

    if REPORT_XML.exists():
        test_results = parse_junit_tests(REPORT_XML)

        for t in test_results:
            save_history({
                "host": t.host,
                "test_type": t.test_type,
                "test_useful": 1 if t.status in ("PASS", "FAIL") else 0
            })

    print(f"[AML] Execução finalizada em {time.time() - start:.2f}s")
