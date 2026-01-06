from doctest import SKIP

import h2o
from h2o.automl import H2OAutoML
from pathlib import Path
from jinja2 import Environment, FileSystemLoader
import json
import time

from utils.metrics import save_metrics
from utils.automl_static_reporter import xml_json_test_reporter
from utils.junit_parser import parse_junit
from utils.junit_to_tests import parse_junit_tests
from utils.automl_postprocess import apply_automl_results
from reports import html
from reports import Report


OUT_DIR = Path("generated_tests")
TEMPLATE_DIR = Path("templates")
HISTORY_FILE = Path("auto_ml_history/history.json")
AUTOML_REPORT_DIR = Path("report/automl")

FEATURE_COLS = [
    "port_count",
    "has_ftp",
    "has_ssh",
    "has_telnet",
    "has_http",
    "has_mqtt",
    "vuln_len",
]

TARGET_COL = "vuln_found"


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
# Feature engineering
# =========================
def build_features(device, vulnerability):
    v = vulnerability.upper()

    return {
        "port_count": len(device.ports),
        "has_ftp": "FTP" in v,
        "has_ssh": "SSH" in v,
        "has_telnet": "TELNET" in v,
        "has_http": "HTTP" in v,
        "has_mqtt": "MQTT" in v,
        "vuln_len": len(v),
    }


# =========================
# AutoML model
# =========================
def train_model(frame):
    aml = H2OAutoML(
        max_models=10,
        max_runtime_secs=60,
        seed=1,
    )
    aml.train(y=TARGET_COL, training_frame=frame)
    return aml.leader


# =========================
# Decide se gera o teste
# =========================
def should_generate_test(model, features):
    row = {k: features[k] for k in FEATURE_COLS}
    frame = h2o.H2OFrame([row])
    pred = model.predict(frame).as_data_frame()
    return int(pred.iloc[0, 0]) == 1

# =========================
# Entry point
# =========================
def generate_tests(iot_devices, args):

    start_time = time.time()

    try:
        h2o.init()
    except Exception as e:
        print("[AML] H2O indisponível:", e)
        return

    history = load_history()
    normalized = []

    for r in history:
        if TARGET_COL not in r:
            continue

        row = {k: r.get(k, 0) for k in FEATURE_COLS}
        row[TARGET_COL] = r[TARGET_COL]
        normalized.append(row)

    print(f"[AML][DEBUG] Histórico normalizado: {len(normalized)} linhas")

    model = None
    labels = {r[TARGET_COL] for r in normalized}

    if len(labels) >= 2:
        frame = h2o.H2OFrame(normalized)
        frame[TARGET_COL] = frame[TARGET_COL].asfactor()
        model = train_model(frame)
        print("[AML] Modelo AutoML treinado com sucesso")
    else:
        print("[AML] Bootstrap: rótulos insuficientes")

    # ---------- Templates ----------
    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    generated = []

    for dev in iot_devices:
        for vuln in dev.vulnerabilities:
            features = build_features(dev, vuln)

            if model and not should_generate_test(model, features):
                continue

            v = vuln.lower()
            if "ftp" in v:
                tpl = "ftp_test.py.j2"
            elif "http" in v or "directory" in v:
                tpl = "http_test.py.j2"
            elif "mqtt" in v:
                tpl = "mqtt_test.py.j2"
            elif "telnet" in v:
                tpl = "telnet_test.py.j2"
            elif "ssh" in v:
                tpl = "ssh_test.py.j2"
            else:
                tpl = "generic_test.py.j2"

            template = env.get_template(tpl)

            fname = f"test_{dev.ip}_{vuln}".lower().replace(" ", "_").replace(".", "_")
            path = OUT_DIR / f"{fname}.py"

            path.write_text(template.render(v={
                "ip": dev.ip,
                "hostname": dev.hostname,
                "ports": ",".join(map(str, dev.ports)),
                "vulnerabilities": vuln,
            }))

            if path.exists():
                generated.append(path)

    print(f"[AML] {len(generated)} testes gerados (AutoML-guided)")

    result = xml_json_test_reporter(OUT_DIR, AUTOML_REPORT_DIR)

    apply_automl_results(
        iot_devices,
        AUTOML_REPORT_DIR / "automl_tests.xml"
    )

    report = Report(args.network, iot_devices, args.output.lower())
    html.report(report, "automl")

    junit_results = parse_junit(AUTOML_REPORT_DIR / "automl_tests.xml")

    total_time = time.time() - start_time

    save_metrics({
        "mode": "automl",
        "devices": len(iot_devices),
        "tests_generated": len(generated),
        "tests_executed": junit_results["passed"] + junit_results["failed"],
        "confirmed_vulns": junit_results["passed"],
        "exec_time_sec": total_time,
    })

    # ---------- Feedback supervisionado ----------
    test_results = parse_junit_tests(AUTOML_REPORT_DIR / "automl_tests.xml")

    for t in test_results:
        if t.status == "SKIP":
            continue  # não aprende com dado inválido


        save_history({
            "test_name": t.name,
            "port_count": 1,
            "has_ftp": t.vuln_id.startswith("FTP"),
            "has_ssh": t.vuln_id.startswith("SSH"),
            "has_telnet": t.vuln_id.startswith("TELNET"),
            "has_http": t.vuln_id.startswith("HTTP"),
            "has_mqtt": t.vuln_id.startswith("MQTT"),
            "vuln_len": len(t.vuln_id),
            "vuln_found": 1 if t.status == "PASS" else 0
        })
