import os
from scanners.nmap_scanner import explore as nmap_explore
# from scanners.scapy_scanner import explore as scapy_explore

import argparse
import logging

from reports import html, json
# from utils.scan import get_local_network, get_local_network
from utils.tester import general_tester
from vulnerability_tester import *
from reports.objects import Report

# SCANNERS: dict = {
#     "nmap": nmap_explore,
#     "scapy": scapy_explore
# }

parser = argparse.ArgumentParser(description="Network scanner for IoT devices")
parser.add_argument("-v", "--verbose", action="store_true", help="Verbose mode")
# parser.add_argument("-a", "--all", action="store_true", help="Run all available scanning methods") ## se usar apenas nmap não precisa de flag
parser.add_argument("-i", "--interface", type=str, default="eth0", help="Network interface to use (default: eth0)") ## não usado
# parser.add_argument("-ip", "--ip", type=str, help="IP address to scan") ## não usado
# parser.add_argument("-m", "--mac", type=str, help="MAC address to scan") ## não usado
parser.add_argument("-n", "--network", type=str, default="auto", help="Network to scan (default: detected /24 network)") ## corrigir de -r para -n
# parser.add_argument("-s", "--scans", type=str, default="", help="Comma-separated scanning methods to run (nmap, scapy)") ## apenas nmap n necessita de flag
parser.add_argument("-o", "--output", type=str, help="Output file name") ## html ou json
parser.add_argument("-p", "--ports", type=str, help="Extra ports to scan (comma-separated)") ## implementar portas extras para teste
parser.add_argument("-t", "--test", action="store_true", help="Run vulnerability tests on discovered devices") ## funcionando

args = parser.parse_args()

if args.verbose:
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
else:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# if args.all:
#     args.scans = ",".join(SCANNERS.keys())

iot_devices = []

# args.network = get_local_network() if args.network == "" else args.network

# scanning with nmap
logging.info(f"Running nmap scan...")
result = nmap_explore(args)
logging.info(f"Nmap scan completed.")
for d in result:
    iot_devices.append(d)


# for scanner in args.scans.split(","):
#     if scanner not in SCANNERS:
#         logging.error(f"Invalid scanner: {scanner}")
#         continue
    
#     logging.info(f"Running {scanner} scan...")
#     result = SCANNERS[scanner](args)

#     for d in result:
#         if d not in iot_devices:
#             iot_devices.append(d)
#         else:
#             iot_devices[iot_devices.index(d)].ports = iot_devices[iot_devices.index(d)].ports + d.ports

#     logging.info(f"{scanner} scan completed.")

# Testing new tester
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
    else:
        print(f"[!] Invalid output format: {ext}. Supported formats are: html, json")
        exit(1)


    print(f"\n[✔] IoT devices identified: {len(report.network.devices)}")
    print(f"[✔] Report saved as {report.timestamp}_{os.path.splitext(ext)[0]}.{ext.split('.')[-1]}")