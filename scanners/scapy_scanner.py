import json
import pyshark
from scapy.all import ARP, Ether, srp, IP, TCP
import socket
from reports.objects import Report, Device
from reports import csv, html, txt, json
from utils import get_local_network
from utils.default_data import HOSTNAME, COMMON_VULN_PORTS, MAC_ADDRESSES

# 1. Scan ARP para descobrir dispositivos ativos
def scan_network(network):
    print(f"🔍 Escaneando rede {network}...")
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

# 2. Verifica portas vulneráveis
def scan_ports(ip, ports, mac_address):
    open_ports = []
    for port in ports:
        pkt = Ether(dst=mac_address)/IP(dst=ip)/TCP(dport=port, flags="S")
        resp = srp(pkt, timeout=1, verbose=0)[0]
        for _, r in resp:
            if r.haslayer(TCP) and r[TCP].flags == 0x12:
                print(f"✅ Porta {port} aberta.")
                open_ports.append(port)
    return open_ports

# 3. Captura pacotes com PyShark para fingerprint
def sniff_device_traffic(interface="eth0", timeout=10):
    print(f"📡 Capturando tráfego na interface {interface}...")
    cap = pyshark.LiveCapture(interface=interface)
    cap.sniff(timeout=timeout)
    return cap

# 4. Tenta identificar dispositivo IoT por fingerprinting simples
def is_iot_device(mac, open_ports):
    return any(mac.upper().startswith(prefix) for prefix in MAC_ADDRESSES) or \
           any(port in COMMON_VULN_PORTS.keys() for port in open_ports)

def explore(args):
    net_ip = get_local_network() if args.network == "auto" else args.network
    output = args.output
    
    devices = scan_network(net_ip)

    print(f"\n📱 Dispositivos encontrados: {len(devices)}\n")

    for device in devices:
        ip = device.ip
        mac = device.mac
        hostname = device.hostname if device.hostname else "Unknown"
        print(f"➡️  Verificando: {hostname} - {ip} ({mac})...")

        open_ports = scan_ports(ip, COMMON_VULN_PORTS.keys(), mac)
        if not open_ports:
            print("  🔒 Nenhuma porta vulnerável encontrada.")
            continue
        print(f"  ⚠️ Portas abertas: {', '.join(f'{p} ({COMMON_VULN_PORTS[p]})' for p in open_ports)}")
        device.ports = open_ports
        if is_iot_device(mac, open_ports):
            device.is_iot = True
            print("  🤖 Possível dispositivo IoT identificado!")
        else:
            print("  📡 Dispositivo genérico.")
            

    report = Report(net_ip, devices, output)

    if output.endswith(".html"):
        html.report(report)
    elif output.endswith(".txt"):
        txt.report(report)
    elif output.endswith(".csv"):
        csv.report(report)
    elif output.endswith(".json"):
        json.report(report)


    print("\n✅ Varredura finalizada.")
    print(f'dispositivos IoT encontrados: {len(devices)}')