
import ipaddress
import socket

def get_local_network():
    hostname = socket.gethostname()
    ip_local = socket.gethostbyname(hostname)
    rede = ipaddress.ip_network(ip_local + '/24', strict=False)
    return str(rede)
