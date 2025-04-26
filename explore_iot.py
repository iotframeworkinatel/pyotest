import socket
import requests
import base64
import pyshark
import time
import psutil
from scapy.all import sr1, IP, TCP

TARGET_IP = "192.168.15.24"
TARGET_MAC = "cc:64:1a:23:1d:f8"
CREDENTIALS = [
    ("admin", "admin"),
    ("admin", "1234"),
    ("root", "root"),
    ("admin", ""),
    ("", "admin"),
]

# 1. DNS reverso
def reverse_dns(ip):
    try:
        return socket.gethostbyaddr(ip)[0]
    except:
        return "Não encontrado"

# 2. Fabricante MAC
def mac_vendor(mac):
    try:
        response = requests.get(f"https://api.macvendors.com/{mac}", timeout=5)
        return response.text
    except:
        return "Desconhecido"

# 3. Checa RTSP (porta 554)
def check_rtsp(ip):
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        sock.connect((ip, 554))
        sock.send(b"OPTIONS rtsp://%s RTSP/1.0\r\nCSeq: 1\r\n\r\n" % ip.encode())
        data = sock.recv(1024)
        sock.close()
        return data.decode()
    except:
        return None

# 4. Testa acesso HTTP com auth básica
def try_http_auth(ip, port=80):
    url = f"http://{ip}:{port}/"
    for user, pw in CREDENTIALS:
        creds = base64.b64encode(f"{user}:{pw}".encode()).decode()
        headers = {"Authorization": f"Basic {creds}"}
        try:
            r = requests.get(url, headers=headers, timeout=3)
            if r.status_code == 200:
                print(f"✅ Sucesso com {user}:{pw}")
                return (user, pw)
        except:
            continue
    return None

# 5. Descobre interface de rede
def get_default_interface():
    for iface, addrs in psutil.net_if_addrs().items():
        for addr in addrs:
            if addr.family == socket.AF_INET and not iface.startswith("lo"):
                return iface
    return "any"

# 6. Captura pacotes com PyShark
def capture_packets(ip, timeout=15):
    interface = get_default_interface()
    print(f"📡 Capturando pacotes para {ip} na interface {interface} por {timeout}s...")
    cap = pyshark.LiveCapture(interface=interface, display_filter=f"ip.addr == {ip}")
    cap.sniff(timeout=timeout)
    for pkt in cap:
        try:
            print(f"{pkt.sniff_time} | {pkt.highest_layer} | {pkt.ip.src} -> {pkt.ip.dst}")
        except AttributeError:
            print("📦 Pacote sem camada IP.")

# 7. Verifica se porta está aberta (TCP SYN scan)
def is_port_open(ip, port):
    pkt = IP(dst=ip)/TCP(dport=port, flags="S")
    resp = sr1(pkt, timeout=2, verbose=0)
    return resp and resp.haslayer(TCP) and resp[TCP].flags == 0x12

# ---------- MAIN ----------
if __name__ == "__main__":
    print(f"🔎 Explorando dispositivo IoT em {TARGET_IP}...\n")

    print("🔗 DNS reverso:", reverse_dns(TARGET_IP))
    print("🏷️  Fabricante MAC:", mac_vendor(TARGET_MAC))

    print("\n🎥 Verificando RTSP...")
    rtsp = check_rtsp(TARGET_IP)
    if rtsp:
        print("✅ RTSP responde:")
        print(rtsp)
    else:
        print("❌ RTSP não respondeu.")

    print("\n🌐 Verificando HTTP e login básico...")
    for port in [80, 8080, 50000]:
        if is_port_open(TARGET_IP, port):
            print(f"✅ Porta {port} está aberta.")
            creds = try_http_auth(TARGET_IP, port)
            if creds:
                print(f"  🔓 Acesso com: {creds[0]}:{creds[1]}")
            else:
                print(f"  🔒 Porta {port} aberta, mas credenciais padrão não funcionaram.")
        else:
            print(f"❌ Porta {port} fechada.")

    print("\n📶 Captura de tráfego em andamento...")
    capture_packets(TARGET_IP)

    print("\n✅ Exploração concluída.")
