import pyshark
from scapy.all import ARP, Ether, srp, IP, TCP, sr
from netaddr import IPNetwork
from datetime import datetime
import socket

# Configurações da rede
NETWORK = "192.168.0.0/24"
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
        ip = received.psrc
        mac = received.hwsrc
        try:
            hostname = socket.gethostbyaddr(ip)[0]
        except socket.herror:
            hostname = None  # Caso não consiga resolver o nome
        devices.append({'ip': ip, 'mac': mac, 'hostname': hostname})
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
    iot_ports = [80, 443, 554, 8883, 8080, 2323, 23, 5678, 6668, 9999]
    return any(mac.upper().startswith(prefix) for prefix in iot_mac_prefixes) or \
           any(port in iot_ports for port in open_ports)

# --- MAIN ---
def pyshark_explore(NETWORK, NOME_ARQUIVO="relatorio.txt"):
    dispositivos_iot = []
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    with open(f"{timestamp}_{NOME_ARQUIVO}", "w", encoding='utf-8') as f:
        f.write(f"Relatório de escaneamento - {timestamp}\n\n")
        f.write(f"Rede: {NETWORK}\n")
        f.write(f"Data: {datetime.now()}\n\n")
        f.write("-" * 40 + "\n")
        devices = scan_network(NETWORK)
        f.write(f"Dispositivos encontrados: {len(devices)}\n")
        print(f"\n📱 Dispositivos encontrados: {len(devices)}\n")

        for device in devices:
            ip = device['ip']
            mac = device['mac']
            hostname = device['hostname'] if device['hostname'] else "Desconhecido"
            f.write(f"Hostname: {hostname}\n")
            f.write(f"IP: {ip}\n")
            f.write(f"MAC: {mac}\n")
            print(f"➡️  Verificando: {hostname} - {ip} ({mac})...")

            open_ports = scan_ports(ip, COMMON_VULN_PORTS.keys(), mac)
            if not open_ports:
                f.write("Nenhuma porta vulnerável encontrada.\n")
                f.write("-" * 40 + "\n")
                print("  🔒 Nenhuma porta vulnerável encontrada.")
                continue
            f.write(f"Portas abertas: {', '.join(map(str, open_ports))}\n")
            print(f"  ⚠️ Portas abertas: {', '.join(f'{p} ({COMMON_VULN_PORTS[p]})' for p in open_ports)}")

            if is_iot_device(mac, open_ports):
                f.write("Dispositivo IoT identificado!\n")
                dispositivos_iot.append(device)
                print("  🤖 Possível dispositivo IoT identificado!")
            else:
                f.write("Dispositivo genérico.\n")
                print("  📡 Dispositivo genérico.")
            f.write("-" * 40 + "\n")    

    print("\n✅ Varredura finalizada.")
    print(f'dispositivos IoT encontrados: {len(dispositivos_iot)}')

if __name__ == "__main__":
    pyshark_explore(NETWORK)