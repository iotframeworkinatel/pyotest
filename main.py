from nmap_scanner import nmap_scanner
from scapy_scanner import scapy_explore

# definindo argumentos de linha de comando
import argparse
import logging
from datetime import datetime

parser = argparse.ArgumentParser(description="Scanner de rede para dispositivos IoT")
parser.add_argument("-v", "--verbose", action="store_true", help="Modo verboso")
parser.add_argument("-a", "--all", action="store_true", help="Executa todos os métodos de escaneamento")
parser.add_argument("-i", "--interface", type=str, default="eth0", help="Interface de rede a ser usada (padrão: eth0)")
parser.add_argument("-ip", "--ip", type=str, help="IP a ser escaneado")
parser.add_argument("-m", "--mac", type=str, help="MAC a ser escaneado")
parser.add_argument("-r", "--rede", type=str, default="192.168.0.0/24", help="Rede a ser escaneada (padrão: 192.168.0.0/24)")
#lista dos scans para executar
parser.add_argument("-s", "--scans", type=str, default="", help="Métodos de escaneamento a serem executados (nmap, scapy)")
parser.add_argument("-o", "--output", type=str, default="relatorio.txt", help="Arquivo de saída para o relatório (padrão: relatorio.txt)")
args = parser.parse_args()

if args.verbose:
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
else:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

if args.all:
    logging.info(f"Escaneando a rede {args.rede} com todos os métodos...")
    nmap_scanner(args.rede, args.output)
    scapy_explore(args.rede, args.output)

if "nmap" in args.scans:
    logging.info("Executando escaneamento Nmap...")
    nmap_scanner(args.rede, args.output)
    logging.info("Escaneamento Nmap concluído.")

if "scapy" in args.scans:
    logging.info("Executando escaneamento Scapy...")
    scapy_explore(args.rede, args.output)
    logging.info("Escaneamento Scapy concluído.")