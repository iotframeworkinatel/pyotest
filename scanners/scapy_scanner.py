import json
import pyshark
from scapy.all import ARP, Ether, srp, IP, TCP
import socket
from reports.objects import Report, Device
from reports import csv, html, txt, json
from utils import get_local_network
from utils.default_data import HOSTNAME, COMMON_VULN_PORTS, MAC_ADDRESSES

# 1. ARP scan to discover active devices
def scan_network(network):
    print(f"🔍 Scanning network {network}...")
    arp = ARP(pdst=network)
    ether = Ether(dst="ff:ff:ff:ff:ff:ff")
    packet = ether / arp

    result = srp(packet, timeout=3, verbose=0)[0]
    devices = []
    for sent, received in result:
        ip = received.psrc
        mac = received.hwsrc
        try:
            hostname = socket.gethostbyaddr(ip)[0]
        except socket.herror:
            hostname = None
        device = Device(ip, mac, hostname)
        devices.append(device)

    return devices

# 2. Check for vulnerable open ports
def scan_ports(ip, ports, mac_address):
    open_ports = []
    for port in ports:
        pkt = Ether(dst=mac_address)/IP(dst=ip)/TCP(dport=port, flags="S")
        resp = srp(pkt, timeout=1, verbose=0)[0]
        for _, r in resp:
            if r.haslayer(TCP) and r[TCP].flags == 0x12:
                print(f"✅ Port {port} is open.")
                open_ports.append(port)
    return open_ports

# 3. Capture packets with PyShark for fingerprinting
def sniff_device_traffic(interface="eth0", timeout=10):
    print(f"📡 Capturing traffic on interface {interface}...")
    cap = pyshark.LiveCapture(interface=interface)
    cap.sniff(timeout=timeout)
    return cap

# 4. Try to identify IoT device by simple fingerprinting
def is_iot_device(mac, open_ports):
    return any(mac.upper().startswith(prefix) for prefix in MAC_ADDRESSES) or \
           any(port in COMMON_VULN_PORTS.keys() for port in open_ports)

def explore(args):
    net_ip = get_local_network() if args.network == "auto" else args.network
    output = "scapy_" + args.output 
    
    devices = scan_network(net_ip)

    print(f"\n📱 Devices found: {len(devices)}\n")

    for device in devices:
        ip = device.ip
        mac = device.mac
        hostname = device.hostname if device.hostname else "Unknown"
        print(f"➡️  Checking: {hostname} - {ip} ({mac})...")

        open_ports = scan_ports(ip, COMMON_VULN_PORTS.keys(), mac)
        if not open_ports:
            print("  🔒 No vulnerable open ports found.")
            continue
        print(f"  ⚠️ Open ports: {', '.join(f'{p} ({COMMON_VULN_PORTS[p]})' for p in open_ports)}")
        device.ports = open_ports
        if is_iot_device(mac, open_ports):
            device.is_iot = True
            print("  🤖 Potential IoT device detected!")
        else:
            print("  📡 Generic network device.")
            

    report = Report(net_ip, devices, output)

    if output.endswith(".html"):
        html.report(report)
    elif output.endswith(".txt"):
        txt.report(report)
    elif output.endswith(".csv"):
        csv.report(report)
    elif output.endswith(".json"):
        json.report(report)

    print("\n✅ Scan completed.")
    print(f"IoT devices found: {len(devices)}")
