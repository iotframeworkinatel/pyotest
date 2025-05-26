import nmap
from utils.default_data import COMMON_VULN_PORTS
from reports.objects import Device
import logging

def ping_scan(network, extra_ports=None):
    logging.info(f"Running Nmap on network {network}...")

    # If extra ports are provided, add them to the common vulnerable ports
    if extra_ports:
        logging.info(f"Adding extra ports to scan: {extra_ports}")
        extra_ports = [int(port.strip()) for port in extra_ports.split(',')]
        for port in extra_ports:
            if port not in COMMON_VULN_PORTS:
                COMMON_VULN_PORTS[port] = "Custom Port"
    # SHow the common vulnerable ports being scanned
    logging.info(f"Scanning for common vulnerable ports: {', '.join(str(port) for port in COMMON_VULN_PORTS.keys())}")

    # Scan the network for live hosts using ARP
    nm_arp = nmap.PortScanner()
    nm_arp.scan(hosts=network, arguments="-sn")

    # Check for silent hosts with vulnerable ports
    ports_to_check = ','.join(str(port) for port in COMMON_VULN_PORTS.keys())
    nm_ports = nmap.PortScanner()
    nm_ports.scan(hosts=network, arguments=f"-T4 -Pn -sT -p {ports_to_check}")

    devices = []

    for host in nm_ports.all_hosts():
        ip = host
        mac = nm_arp[host]['addresses'].get('mac', 'Unknown') if host in nm_arp.all_hosts() else 'Unknown'
        hostname = None
        if 'hostnames' in nm_ports[host] and nm_ports[host]['hostnames']:
            hostname = nm_ports[host]['hostnames'][0].get('name', None)

        open_ports = []
        tcp_ports = nm_ports[host].get('tcp', {})
        for port, info in tcp_ports.items():
            if info.get('state') == 'open':
                open_ports.append(port)

        if not open_ports:
            continue

        device = Device(ip=ip, mac=mac, hostname=hostname, ports=open_ports, is_iot=True)
        devices.append(device)

    logging.info(f"{len(devices)} devices found.")
    return devices

def explore(args):
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
    else:
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    devices = ping_scan(args.network, args.ports)
    iot_devices = []

    for d in devices:
        iot_devices.append(d)

        logging.info(f"{'[IoT]' if d.is_iot else '[---]'} {d.ip} | {d.mac} | {d.hostname} | Ports: {d.ports}")

    return iot_devices