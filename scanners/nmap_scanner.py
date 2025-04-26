import nmap
from datetime import datetime
from utils import get_local_network
from utils.default_data import HOSTNAME, COMMON_VULN_PORTS
from reports.objects import Device, Report
from reports import csv, html, txt, json
import os
from vulnerability_tester import test_ssh_weak_auth


def ping_scan(network):
    print(f"[+] Running Nmap on network {network}...")
    nm = nmap.PortScanner()
    nm.scan(hosts=network, arguments="-sn")
    devices = []

    for host in nm.all_hosts():
        ip = nm[host]['addresses'].get('ipv4')
        mac = nm[host]['addresses'].get('mac', 'Unknown')
        hostname = nm[host]['hostnames'][0]['name'] if nm[host]['hostnames'] else None

        devices.append(Device(ip=ip, mac=mac, hostname=hostname))

    print(f"[+] {len(devices)} devices found.")
    return devices

def scan_ports(ip):
    nm = nmap.PortScanner()
    open_ports = []
    try:
        nm.scan(ip, arguments='-T4 -F')
        if ip in nm.all_hosts():
            ports = nm[ip].get('tcp', {})
            open_ports = list(ports.keys())
    except Exception as e:
        print(f"[!] Error scanning ports on {ip}: {e}")
    return open_ports

def iot_heuristic(device: Device):
    hostname = (device.hostname or "").lower()
    ports_set = set(device.ports or [])

    suspicious_by_hostname = any(term in hostname for term in HOSTNAME)
    suspicious_by_port = any(p in ports_set for p in COMMON_VULN_PORTS.keys())

    return suspicious_by_hostname or suspicious_by_port

def explore(args):
    network_ip = get_local_network() if args.network == "auto" else args.network
    output = "nmap_" + args.output 
    devices = ping_scan(network_ip)
    iot_devices = []

    for d in devices:
        d.ports = scan_ports(d.ip)
        d.is_iot = iot_heuristic(d)

        if d.is_iot:
            iot_devices.append(d)

        print(f"{'[IoT]' if d.is_iot else '[---]'} {d.ip} | {d.mac} | {d.hostname} | Ports: {d.ports}")

        if 22 in d.ports:
            print("\n")
            print(f"🔑 Testing SSH weak authentication on {d.ip}...")
            test_ssh_weak_auth(d.ip)
            print("\n")

    report = Report(network_ip, iot_devices, output)

    ext = output.lower()
    if ext.endswith(".html"):
        html.report(report)
    elif ext.endswith(".csv"):
        csv.report(report)
    elif ext.endswith(".json"):
        json.report(report)
    else:
        txt.report(report)

    print(f"\n[✔] IoT devices identified: {len(iot_devices)}")
    print(f"[✔] Report saved as {report.timestamp}_{os.path.splitext(output)[0]}.{ext.split('.')[-1]}")
