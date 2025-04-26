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
    print(f"[+] Running scapy scan on network {network}...")
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
    
    print(f"[+] {len(devices)} devices found.")
    return devices

# 2. Check for vulnerable open ports
def scan_ports(ip, ports, mac_address):
    open_ports = []
    for port in ports:
        pkt = Ether(dst=mac_address)/IP(dst=ip)/TCP(dport=port, flags="S")
        resp = srp(pkt, timeout=1, verbose=0)[0]
        for _, r in resp:
            if r.haslayer(TCP) and r[TCP].flags == 0x12:
                open_ports.append(port)
    return open_ports


# 3. Try to identify IoT device by simple fingerprinting
def is_iot_device(mac, open_ports):
    return any(mac.upper().startswith(prefix) for prefix in MAC_ADDRESSES) or \
           any(port in COMMON_VULN_PORTS.keys() for port in open_ports)

def explore(args):
    net_ip = get_local_network() if args.network == "auto" else args.network
    devices = scan_network(net_ip)
    iot_devices = []

    for device in devices:
        ip = device.ip
        mac = device.mac
        hostname = device.hostname if device.hostname else "Unknown"
        device.ports = scan_ports(ip, COMMON_VULN_PORTS.keys(), mac)
        device.is_iot = is_iot_device(mac, device.ports)
        
        if device.is_iot:
            iot_devices.append(device)
        
        print(f"{'[IoT]' if device.is_iot else '[---]'} {ip} | {mac} | {hostname} | Ports: {open_ports}")
       
    report = Report(net_ip, iot_devices)

    return report