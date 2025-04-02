import nmap
from datetime import datetime

REDE_LOCAL = "192.168.15.0/24"

# Critérios alternativos para identificar IoT
PORTAS_IOT = [80, 443, 554, 8883, 8080, 2323, 23, 5678, 6668, 9999]
HOSTNAMES_SUSPEITOS = ["camera", "tuya", "smart", "iot", "ipcam", "unknown", "device", "esp", "tplink", "dlink", "sonoff", "light", "plug", "bulb", "roku", "tv", "android", "iphone"]

def escanear_rede_ping(rede):
    print(f"[+] Rodando Nmap na rede {rede}...")
    nm = nmap.PortScanner()
    nm.scan(hosts=rede, arguments="-sn")
    dispositivos = []

    for host in nm.all_hosts():
        ip = nm[host]['addresses'].get('ipv4')
        mac = nm[host]['addresses'].get('mac', 'Desconhecido')
        hostname = nm[host]['hostnames'][0]['name'] if nm[host]['hostnames'] else ''

        dispositivos.append({
            'ip': ip,
            'mac': mac,
            'hostname': hostname
        })

    print(f"[+] {len(dispositivos)} dispositivos encontrados.")
    return dispositivos

def escanear_portas(ip):
    nm = nmap.PortScanner()
    portas_abertas = {}
    try:
        nm.scan(ip, arguments='-T4 -F')  # Fast scan
        if ip in nm.all_hosts():
            portas = nm[ip].get('tcp', {})
            portas_abertas = {p: portas[p]['name'] for p in portas}
    except Exception as e:
        print(f"[!] Erro ao escanear portas de {ip}: {e}")
    return portas_abertas

def heuristica_iot(device):
    hostname = device['hostname'].lower()
    portas = device.get('portas', {})
    portas_set = set(portas.keys())

    suspeito_por_hostname = any(term in hostname for term in HOSTNAMES_SUSPEITOS)
    suspeito_por_porta = any(p in portas_set for p in PORTAS_IOT)

    return suspeito_por_hostname or suspeito_por_porta

def nmap_scanner(REDE_LOCAL):
    dispositivos = escanear_rede_ping(REDE_LOCAL)

    dispositivos_info = []
    dispositivos_iot = []

    for d in dispositivos:
        portas = escanear_portas(d["ip"])
        d["portas"] = portas
        d["is_iot"] = heuristica_iot(d)

        if d["is_iot"]:
            dispositivos_iot.append(d)

        dispositivos_info.append(d)

        print(f"{'[IoT]' if d['is_iot'] else '[---]'} {d['ip']} | {d['mac']} | {d['hostname']} | Portas: {list(portas.keys())}")

    # Salvar resultado em dicionário
    resultado = {
        "todos_dispositivos": dispositivos_info,
        "dispositivos_iot": dispositivos_iot
    }

    # Exportar relatório simples
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    with open(f"relatorio_iot_{timestamp}.txt", "w") as f:
        for d in dispositivos_iot:
            f.write(f"IP: {d['ip']}\n")
            f.write(f"MAC: {d['mac']}\n")
            f.write(f"Hostname: {d['hostname']}\n")
            f.write(f"Portas abertas: {d['portas']}\n")
            f.write("-" * 40 + "\n")

    print(f"\n[✔] Dispositivos IoT identificados: {len(dispositivos_iot)}")
    print(f"[✔] Relatório salvo como relatorio_iot_{timestamp}.txt")

if __name__ == "__main__":
    nmap_scanner(REDE_LOCAL)