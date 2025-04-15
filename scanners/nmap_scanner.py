import nmap
from datetime import datetime
from utils import get_local_network
from utils.default_data import HOSTNAME, COMMON_VULN_PORTS
from reports.objects import Device, Report
from reports import csv, html, txt, json
import os


def escanear_rede_ping(rede):
    print(f"[+] Rodando Nmap na rede {rede}...")
    nm = nmap.PortScanner()
    nm.scan(hosts=rede, arguments="-sn")
    dispositivos = []

    for host in nm.all_hosts():
        ip = nm[host]['addresses'].get('ipv4')
        mac = nm[host]['addresses'].get('mac', 'Desconhecido')
        hostname = nm[host]['hostnames'][0]['name'] if nm[host]['hostnames'] else None

        dispositivos.append(Device(ip=ip, mac=mac, hostname=hostname))

    print(f"[+] {len(dispositivos)} dispositivos encontrados.")
    return dispositivos

def escanear_portas(ip):
    nm = nmap.PortScanner()
    portas_abertas = []
    try:
        nm.scan(ip, arguments='-T4 -F')
        if ip in nm.all_hosts():
            portas = nm[ip].get('tcp', {})
            portas_abertas = list(portas.keys())
    except Exception as e:
        print(f"[!] Erro ao escanear portas de {ip}: {e}")
    return portas_abertas

def heuristica_iot(device: Device):
    hostname = (device.hostname or "").lower()
    portas_set = set(device.ports or [])

    suspeito_por_hostname = any(term in hostname for term in HOSTNAME)
    suspeito_por_porta = any(p in portas_set for p in COMMON_VULN_PORTS.keys())

    return suspeito_por_hostname or suspeito_por_porta

def explore(args):
    rede_local = get_local_network() if args.network == "auto" else args.network
    output = args.output

    dispositivos = escanear_rede_ping(rede_local)
    dispositivos_iot = []

    for d in dispositivos:
        d.ports = escanear_portas(d.ip)
        d.is_iot = heuristica_iot(d)

        if d.is_iot:
            dispositivos_iot.append(d)

        print(f"{'[IoT]' if d.is_iot else '[---]'} {d.ip} | {d.mac} | {d.hostname} | Portas: {d.ports}")

    report = Report(rede_local, dispositivos_iot, output)

    ext = output.lower()
    if ext.endswith(".html"):
        html.report(report)
    elif ext.endswith(".csv"):
        csv.report(report)
    elif ext.endswith(".json"):
        json.report(report)
    else:
        txt.report(report)

    print(f"\n[✔] Dispositivos IoT identificados: {len(dispositivos_iot)}")
    print(f"[✔] Relatório salvo como {report.timestamp}_{os.path.splitext(output)[0]}.{ext.split('.')[-1]}")
