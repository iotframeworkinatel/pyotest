from nmap_scanner import nmap_scanner
from scapy_scanner import scapy_explore

import argparse
import logging
from datetime import datetime

parser = argparse.ArgumentParser(description="Network scanner for IoT devices")
parser.add_argument("-v", "--verbose", action="store_true", help="Verbose mode")
parser.add_argument("-a", "--all", action="store_true", help="Run all available scanning methods")
parser.add_argument("-i", "--interface", type=str, default="eth0", help="Network interface to use (default: eth0)")
parser.add_argument("-ip", "--ip", type=str, help="IP address to scan")
parser.add_argument("-m", "--mac", type=str, help="MAC address to scan")
parser.add_argument("-r", "--network", type=str, default="192.168.0.0/24", help="Network to scan (default: 192.168.0.0/24)")
parser.add_argument("-s", "--scans", type=str, default="", help="Comma-separated scanning methods to run (nmap, scapy)")
parser.add_argument("-o", "--output", type=str, default="report.txt", help="Output file name (default: report.txt)")

args = parser.parse_args()

if args.verbose:
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
else:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

if args.all:
    logging.info(f"Scanning network {args.network} with all methods...")
    nmap_scanner(args.network, args.output)
    scapy_explore(args.network, args.output)

if "nmap" in args.scans:
    logging.info("Running Nmap scan...")
    nmap_scanner(args.network, args.output)
    logging.info("Nmap scan completed.")

if "scapy" in args.scans:
    logging.info("Running Scapy scan...")
    scapy_explore(args.network, args.output)
    logging.info("Scapy scan completed.")
