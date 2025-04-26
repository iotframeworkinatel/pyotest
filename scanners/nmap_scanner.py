import nmap
from utils.default_data import HOSTNAME, COMMON_VULN_PORTS
from reports.objects import Device

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
    devices = ping_scan(args.network)
    iot_devices = []

    for d in devices:
        d.ports = scan_ports(d.ip)
        d.is_iot = iot_heuristic(d)

        if d.is_iot:
            iot_devices.append(d)

        print(f"{'[IoT]' if d.is_iot else '[---]'} {d.ip} | {d.mac} | {d.hostname} | Ports: {d.ports}")

    return iot_devices