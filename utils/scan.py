
# import ipaddress
# import socket
# import netifaces

# def get_local_network():
#     for interface in netifaces.interfaces():
#         addresses = netifaces.ifaddresses(interface)
#         if socket.AF_INET in addresses:
#             for addr_info in addresses[socket.AF_INET]:
#                 ip_address = addr_info.get('addr')
#                 if ip_address and ip_address.startswith('192'):
#                     try:
#                         rede = ipaddress.ip_network(ip_address + '/24', strict=False)
#                         return str(rede)
#                     except ValueError:
#                         pass
#     return None