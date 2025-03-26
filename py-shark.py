import pyshark
from scapy.all import ARP, Ether, srp, IP, TCP, sr
from netaddr import IPNetwork
import socket

# Configurações da rede
NETWORK = "192.168.15.0/24"
COMMON_VULN_PORTS = {
    23: "Telnet",
    21: "FTP",
    80: "HTTP",
    554: "RTSP",
    2323: "Telnet alternativa",
    8080: "HTTP alternativa",
    1900: "UPnP",
    50000: "iiimsf"
}

# 1. Scan ARP para descobrir dispositivos ativos
def scan_network(network):
    print(f"🔍 Escaneando rede {network}...")
    arp = ARP(pdst=network)
    ether = Ether(dst="ff:ff:ff:ff:ff:ff")
    packet = ether / arp

    result = srp(packet, timeout=3, verbose=0)[0]
    devices = []
    for sent, received in result:
        devices.append({'ip': received.psrc, 'mac': received.hwsrc})
    return devices

# 2. Verifica portas vulneráveis
def scan_ports(ip, ports, mac_address):
    open_ports = []
    for port in ports:
        # print(f"🔍 Escaneando porta {port}...")
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
    iot_mac_prefixes = ['00:1A:11', '00:1E:C0', '18:B4:30', 'F4:F5:D8']  # Exemplo
    iot_ports = [23, 2323, 554, 1900, 8080, 50000]
    return any(mac.upper().startswith(prefix) for prefix in iot_mac_prefixes) or \
           any(port in iot_ports for port in open_ports)

# --- MAIN ---
if __name__ == "__main__":
    devices = scan_network(NETWORK)
    print(f"\n📱 Dispositivos encontrados: {len(devices)}\n")

    for device in devices:
        ip = device['ip']
        mac = device['mac']
        print(f"➡️  Verificando {ip} ({mac})...")

        open_ports = scan_ports(ip, COMMON_VULN_PORTS.keys(), mac)
        if not open_ports:
            print("  🔒 Nenhuma porta vulnerável encontrada.")
            continue

        print(f"  ⚠️ Portas abertas: {', '.join(f'{p} ({COMMON_VULN_PORTS[p]})' for p in open_ports)}")

        if is_iot_device(mac, open_ports):
            print("  🤖 Possível dispositivo IoT identificado!")
        else:
            print("  📡 Dispositivo genérico.")

    print("\n✅ Varredura finalizada.")
