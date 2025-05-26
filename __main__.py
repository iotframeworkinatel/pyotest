import os
from scanners.nmap_scanner import explore as nmap_explore

import argparse
import logging

from reports import html, json, csv
from utils.tester import general_tester
from vulnerability_tester import *
from reports.objects import Report

parser = argparse.ArgumentParser(description="Network scanner for IoT devices")
parser.add_argument("-v", "--verbose", action="store_true", help="Verbose mode")
parser.add_argument("-n", "--network", type=str, default="192.168.0.0/27", help="Network to scan (e.g., 192.168.15.0/24)")
parser.add_argument("-o", "--output", type=str, help="Output file format (e.g., html, json, csv)") 
parser.add_argument("-p", "--ports", type=str, help="Extra ports to scan (comma-separated e.g., 80,443)") 
parser.add_argument("-t", "--test", action="store_true", help="Run vulnerability tests on discovered devices") 

args = parser.parse_args()

if args.verbose:
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
else:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

iot_devices = []

# scanning with nmap
logging.info(f"Running nmap scan...")
result = nmap_explore(args)
logging.info(f"Nmap scan completed.")
for d in result:
    iot_devices.append(d)


# Testing devices
if args.test:
    iot_devices = general_tester(iot_devices)


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
        print(f"[!] Invalid output format: {ext}. Supported formats are: html, json and csv")
        exit(1)


    print(f"\n[✔] IoT devices identified: {len(report.network.devices)}")
    print(f"[✔] Report saved as {report.timestamp}_{os.path.splitext(ext)[0]}.{ext.split('.')[-1]}")

exit(0)