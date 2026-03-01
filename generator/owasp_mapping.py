"""
OWASP IoT Top 10 mapping for all vulnerability test types.
Maps vulnerability_type → OWASP IoT category.
"""

OWASP_IOT_MAP = {
    "auth": "IoT-01: Weak, Guessable, or Hardcoded Passwords",
    "exposed_service": "IoT-02: Insecure Network Services",
    "exposed_interface": "IoT-02: Insecure Network Services",
    "authorization": "IoT-03: Insecure Ecosystem Interfaces",
    "injection": "IoT-03: Insecure Ecosystem Interfaces",
    "version": "IoT-04: Lack of Secure Update Mechanism",
    "crypto": "IoT-05: Use of Insecure or Outdated Components",
    "info_disclosure": "IoT-06: Insufficient Privacy Protection",
    "information_disclosure": "IoT-06: Insufficient Privacy Protection",
    "fingerprinting": "IoT-06: Insufficient Privacy Protection",
    "path_traversal": "IoT-07: Insecure Data Transfer and Storage",
    "misconfiguration": "IoT-09: Insecure Default Settings",
    "hardening": "IoT-09: Insecure Default Settings",
    "policy": "IoT-10: Lack of Physical Hardening",
    "bruteforce": "IoT-01: Weak, Guessable, or Hardcoded Passwords",
}

# Severity mapping for vulnerability types
SEVERITY_MAP = {
    "auth": "critical",
    "injection": "critical",
    "path_traversal": "high",
    "authorization": "high",
    "exposed_service": "high",
    "exposed_interface": "high",
    "misconfiguration": "medium",
    "crypto": "medium",
    "hardening": "medium",
    "version": "medium",
    "info_disclosure": "medium",
    "information_disclosure": "medium",
    "fingerprinting": "low",
    "policy": "low",
    "bruteforce": "high",
}


def get_owasp_category(vulnerability_type: str) -> str:
    return OWASP_IOT_MAP.get(vulnerability_type, "IoT-09: Insecure Default Settings")


def get_severity(vulnerability_type: str) -> str:
    return SEVERITY_MAP.get(vulnerability_type, "medium")
