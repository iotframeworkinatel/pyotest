"""
Registry of ADAPTIVE-ONLY test variants.
These tests are ONLY executed by the AutoML/adaptive strategy, never by the static suite.
Format matches PROTOCOL_TESTS: (test_func, test_id, test_type, auth_required)
"""

from vulnerability_tester.http.http_adaptive import (
    test_http_sensitive_files_extended,
    test_http_open_admin_extended,
    test_http_cors_misconfiguration,
    test_http_insecure_cookies,
    test_http_trace_method,
    test_http_default_credentials_extended,
    test_http_directory_traversal_encoded,
    test_http_sqli_probe,
)
from vulnerability_tester.coap.coap_adaptive import (
    test_coap_hidden_resource,
    test_coap_put_allowed,
    test_coap_delete_allowed,
)
from vulnerability_tester.modbustcp.modbus_adaptive import (
    test_modbus_write_coil,
    test_modbus_read_input_registers,
    test_modbus_read_discrete_inputs,
    test_modbus_read_coils,
    test_modbus_write_register,
)
from vulnerability_tester.mqtt.mqtt_adaptive import (
    test_mqtt_retained_messages,
    test_mqtt_wildcard_subscribe,
    test_mqtt_sensitive_topic_access,
)
from vulnerability_tester.ssh.ssh_adaptive import (
    test_ssh_weak_auth_extended,
    test_ssh_key_exchange_weak,
)
from vulnerability_tester.ftp.ftp_adaptive import (
    test_ftp_anonymous_real,
    test_ftp_weak_credentials_extended,
)
from vulnerability_tester.dns.dns_adaptive import (
    test_dns_cache_snoop,
    test_dns_any_query,
    test_dns_version_disclosure,
)


ADAPTIVE_TESTS = {
    "http": [
        (test_http_sensitive_files_extended, "http_sensitive_files_ext", "info_disclosure", False),
        (test_http_open_admin_extended, "http_open_admin_ext", "exposed_interface", False),
        (test_http_cors_misconfiguration, "http_cors_misconfig", "misconfiguration", False),
        (test_http_insecure_cookies, "http_insecure_cookies", "hardening", False),
        (test_http_trace_method, "http_trace_method", "misconfiguration", False),
        (test_http_default_credentials_extended, "http_default_creds_ext", "auth", True),
        (test_http_directory_traversal_encoded, "http_traversal_encoded", "path_traversal", False),
        (test_http_sqli_probe, "http_sqli_probe", "injection", False),
    ],

    "coap": [
        (test_coap_hidden_resource, "coap_hidden_resource", "auth", False),
        (test_coap_put_allowed, "coap_put_allowed", "misconfiguration", False),
        (test_coap_delete_allowed, "coap_delete_allowed", "misconfiguration", False),
    ],

    "modbus": [
        (test_modbus_write_coil, "modbus_write_coil", "auth", False),
        (test_modbus_read_input_registers, "modbus_read_input_reg", "auth", False),
        (test_modbus_read_discrete_inputs, "modbus_read_discrete", "auth", False),
        (test_modbus_read_coils, "modbus_read_coils", "auth", False),
        (test_modbus_write_register, "modbus_write_register", "auth", False),
    ],

    "mqtt": [
        (test_mqtt_retained_messages, "mqtt_retained_messages", "info_disclosure", False),
        (test_mqtt_wildcard_subscribe, "mqtt_wildcard_sub", "authorization", False),
        (test_mqtt_sensitive_topic_access, "mqtt_sensitive_topics", "info_disclosure", False),
    ],

    "ssh": [
        (test_ssh_weak_auth_extended, "ssh_weak_auth_ext", "auth", True),
        (test_ssh_key_exchange_weak, "ssh_weak_kex", "crypto", False),
    ],

    "ftp": [
        (test_ftp_anonymous_real, "ftp_anonymous_real", "auth", False),
        (test_ftp_weak_credentials_extended, "ftp_weak_creds_ext", "auth", True),
    ],

    "dns": [
        (test_dns_cache_snoop, "dns_cache_snoop", "info_disclosure", False),
        (test_dns_any_query, "dns_any_query", "misconfiguration", False),
        (test_dns_version_disclosure, "dns_version_disclosure", "fingerprinting", False),
    ],
}
