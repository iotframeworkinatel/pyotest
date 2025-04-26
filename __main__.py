from scanners.nmap_scanner import explore as nmap_explore
from scanners.scapy_scanner import explore as scapy_explore

import argparse
import logging

parser = argparse.ArgumentParser(description="Network scanner for IoT devices")
parser.add_argument("-v", "--verbose", action="store_true", help="Verbose mode")
parser.add_argument("-a", "--all", action="store_true", help="Run all available scanning methods")
parser.add_argument("-i", "--interface", type=str, default="eth0", help="Network interface to use (default: eth0)")
parser.add_argument("-ip", "--ip", type=str, help="IP address to scan")
parser.add_argument("-m", "--mac", type=str, help="MAC address to scan")
parser.add_argument("-r", "--network", default="auto",type=str, help="Network to scan (default: detected /24 network)")
parser.add_argument("-s", "--scans", type=str, default="", help="Comma-separated scanning methods to run (nmap, scapy)")
parser.add_argument("-o", "--output", type=str, default="report.txt", help="Output file name (default: report.txt)")
parser.add_argument("-p", "--ports", type=str, help="Extra ports to scan (comma-separated)")

args = parser.parse_args()

if args.verbose:
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
else:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

if "nmap" in args.scans or args.all:
    logging.info("Running Nmap scan...")
    nmap_explore(args)
    logging.info("Nmap scan completed.")

if "scapy" in args.scans or args.all:
    logging.info("Running Scapy scan...")
    scapy_explore(args)
    logging.info("Scapy scan completed.")
