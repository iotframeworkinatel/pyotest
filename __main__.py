import os
from scanners.nmap_scanner import explore as nmap_explore
from scanners.scapy_scanner import explore as scapy_explore

import argparse
import logging

from reports import csv, html, txt, json
from utils.scan import get_local_network, get_local_network
from utils.tester import general_tester
from vulnerability_tester import *
from reports.objects import Device, Report

SCANNERS: dict = {
    "nmap": nmap_explore,
    "scapy": scapy_explore
}

parser = argparse.ArgumentParser(description="Network scanner for IoT devices")
parser.add_argument("-v", "--verbose", action="store_true", help="Verbose mode")
parser.add_argument("-a", "--all", action="store_true", help="Run all available scanning methods")
parser.add_argument("-i", "--interface", type=str, default="eth0", help="Network interface to use (default: eth0)")
parser.add_argument("-ip", "--ip", type=str, help="IP address to scan")
parser.add_argument("-m", "--mac", type=str, help="MAC address to scan")
parser.add_argument("-r", "--network", type=str, default="auto", help="Network to scan (default: detected /24 network)")
parser.add_argument("-s", "--scans", type=str, default="", help="Comma-separated scanning methods to run (nmap, scapy)")
parser.add_argument("-o", "--output", type=str, help="Output file name")
parser.add_argument("-p", "--ports", type=str, help="Extra ports to scan (comma-separated)")
parser.add_argument("-t", "--test", action="store_true", help="Run vulnerability tests on discovered devices")

args = parser.parse_args()

if args.verbose:
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
else:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

if args.all:
    args.scans = ",".join(SCANNERS.keys())

iot_devices = []

args.network = get_local_network() if args.network == "auto" else args.network

for scanner in args.scans.split(","):
    if scanner not in SCANNERS:
        logging.error(f"Invalid scanner: {scanner}")
        continue
    
    logging.info(f"Running {scanner} scan...")
    result = SCANNERS[scanner](args)

    for d in result:
        if d not in iot_devices:
            iot_devices.append(d)
        else:
            iot_devices[iot_devices.index(d)].ports = iot_devices[iot_devices.index(d)].ports + d.ports

    logging.info(f"{scanner} scan completed.")

# Testing new tester
if args.test:
    iot_devices = general_tester(iot_devices)

# for d in iot_devices:
#     if 22 in d.ports:
#         print(f"\nTesting SSH weak authentication on {d.ip}...")
#         test_ssh_weak_auth(d.ip)

#     if 21 in d.ports:
#         print(f"\nTesting anonymous FTP on {d.ip}...")
#         check_anonymous_ftp(d.ip)

#     for port in d.ports:
#         print(f"\nGrabbing banner on {d.ip}...")
#         grab_banner(d.ip, port)    

if args.output and len(iot_devices) > 0:
    if not os.path.exists("report"):
        os.makedirs("report")
    ext = args.output.lower()
    report = Report(args.network, iot_devices, ext)
    if ext.endswith(".html"):
        html.report(report)
    elif ext.endswith(".csv"):
        csv.report(report)
    elif ext.endswith(".json"):
        json.report(report)
    else:
        txt.report(report)

    print(f"\n[✔] IoT devices identified: {len(report.network.devices)}")
    print(f"[✔] Report saved as {report.timestamp}_{os.path.splitext(ext)[0]}.{ext.split('.')[-1]}")