# utils/protocols.py

"""
Definições centrais de protocolos, portas e requisitos de autenticação
para todos os módulos do framework.
"""

# 🔹 Portas padrão e protocolos associados
PORT_PROTOCOL_MAP = {
    21: "ftp",
    22: "ssh",
    23: "telnet",
    53: "dns",
    80: "http",
    1883: "mqtt",
    554: "rtsp",
    5683: "coap",
    502: "modbus",
}

# 🔹 Protocolos que requerem autenticação
AUTH_REQUIRED = {"ftp", "ssh", "telnet", "http", "mqtt"}

def guess_protocol(port: int) -> str:
    """Dado um número de porta, retorna o protocolo correspondente."""
    return PORT_PROTOCOL_MAP.get(port, "generic")

def requires_auth(protocol: str) -> bool:
    """Verifica se o protocolo requer autenticação."""
    return protocol in AUTH_REQUIRED
