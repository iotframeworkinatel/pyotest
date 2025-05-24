import nmap
from utils.default_data import HOSTNAME, COMMON_VULN_PORTS
from reports.objects import Device


def ping_scan(network):
    print(f"[+] Running Nmap on network {network}...")

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

        device = Device(ip=ip, mac=mac, hostname=hostname)
        device.ports = open_ports
        devices.append(device)

    print(f"[+] {len(devices)} devices found.")
    return devices

def scan_ports(ip):
    nm = nmap.PortScanner()
    open_ports = []
    try:
        ports_to_check = ','.join(str(port) for port in COMMON_VULN_PORTS.keys())
        nm.scan(ip, arguments=f'-T4 -p {ports_to_check}')
        if ip in nm.all_hosts():
            ports = nm[ip].get('tcp', {})
            for port, port_data in ports.items():
                if port_data.get('state') == 'open':
                    open_ports.append(port)
    except Exception as e:
        print(f"[!] Error scanning ports on {ip}: {e}")
    return open_ports

def iot_heuristic(device: Device):
    hostname = (device.hostname or "")
    ports_set = set(device.ports or [])

    suspicious_by_hostname = any(term in hostname for term in HOSTNAME)
    suspicious_by_port = any(p in ports_set for p in COMMON_VULN_PORTS.keys())
    return suspicious_by_hostname or suspicious_by_port

def explore(args):
    devices = ping_scan(args.network)
    iot_devices = []

    for d in devices:
        # d.ports = scan_ports(d.ip)
        d.is_iot = iot_heuristic(d)

        if d.is_iot:
            iot_devices.append(d)

        print(f"{'[IoT]' if d.is_iot else '[---]'} {d.ip} | {d.mac} | {d.hostname} | Ports: {d.ports}")

    return iot_devices