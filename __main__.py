import os

from analysis.generate_plots import generate_plots
from automl.pipeline import run_automl
from experiments.manager import ExperimentManager
from scanners.nmap_scanner import explore as nmap_explore

import argparse
import logging

from reports import html, json, csv
from utils.run_adaptive_tests import run_adaptive_tests
from utils.tester import general_tester
from reports.objects import Report


parser = argparse.ArgumentParser(description="Network scanner for IoT devices")
parser.add_argument("-v", "--verbose", action="store_true", help="Verbose mode")
parser.add_argument("-n", "--network", type=str, default="192.168.0.0/27", help="Network to scan (e.g., 192.168.15.0/24)")
parser.add_argument("-o", "--output", type=str, help="Output file format (e.g., html, json, csv)") 
parser.add_argument("-p", "--ports", type=str, help="Extra ports to scan (comma-separated e.g., 80,443)") 
parser.add_argument("-t", "--test", action="store_true", help="Run vulnerability tests on discovered devices")
parser.add_argument("-aml", "--automl", action="store_true", help="Run automl to automatic generate test cases")

args = parser.parse_args()

if args.verbose:
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
else:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

iot_devices = []
experiment = ExperimentManager()


history_path = experiment.path("history.csv")
metrics_static_path = experiment.path("metrics_static.json")
metrics_automl_path = experiment.path("metrics_automl.json")
automl_tests_path = experiment.path("automl_tests.csv")

# scanning with nmap
logging.info(f"Running nmap scan...")
result = nmap_explore(args)
logging.info(f"Nmap scan completed.")
for d in result:
    iot_devices.append(d)

if args.automl:

    logging.info(f"Running AutoML to generate test cases for...")
    iot_devices = general_tester(iot_devices, experiment, args)
    adaptive_tests = run_automl(iot_devices, experiment)
    run_adaptive_tests(adaptive_tests, iot_devices, experiment, args)
    generate_plots()

elif args.test:
    iot_devices = general_tester(iot_devices, experiment, args)


if args.output and len(iot_devices) > 0:
    if not os.path.exists("report"):
        os.makedirs("report")
    ext = args.output.lower()
    report = Report(args.network, iot_devices, ext)
    if ext.endswith("html"):
        html.report(report)
    elif ext.endswith("json"):
        json.report(report)
    elif ext.endswith("csv"):
        csv.report(report)
    else:
        logging.warning(f"Invalid output format: {ext}. Supported formats are: html, json and csv")
        exit(1)

    logging.info(f"IoT devices identified: {len(report.network.devices)}")
    logging.info(f"Report saved as {report.timestamp}_vulnerability_report.{args.output.lower()}")


exit(0)