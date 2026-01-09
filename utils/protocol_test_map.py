from vulnerability_tester import *
from vulnerability_tester.http.http_dangerous_methods import test_http_dangerous_methods
from vulnerability_tester.http.http_missing_security_headers import test_http_missing_security_headers
from vulnerability_tester.http.http_no_auth import test_http_no_auth
from vulnerability_tester.http.http_open_admin import test_http_open_admin
from vulnerability_tester.http.http_sensitive_files import test_http_sensitive_files
from vulnerability_tester.http.http_verbose_server_header import test_http_verbose_server_header
from vulnerability_tester.mqtt.mqtt_anon_publish import test_mqtt_anonymous_publish
from vulnerability_tester.mqtt.mqtt_acl_bypass import test_mqtt_acl_bypass
from vulnerability_tester.mqtt.mqtt_topic_enum import test_mqtt_topic_enum
from vulnerability_tester.ssh.ssh_no_auth_limit import test_ssh_no_auth_limit
from vulnerability_tester.ssh.ssh_old_version import test_ssh_old_version
from vulnerability_tester.ssh.ssh_password_auth_enabled import test_ssh_password_auth_enabled
from vulnerability_tester.ssh.ssh_root_login import test_ssh_root_login
from vulnerability_tester.ssh.ssh_weak_crypto import test_ssh_weak_crypto

PROTOCOL_TESTS = {

    "banner_grabbing": [
        (grab_banner, "banner_grab", "auth", False),
    ],

    "ftp": [
        (test_ftp_anonymous_login, "ftp_anonymous_login", "auth", False),
    ],

    "http": [
        (test_http_default_credentials, "http_default_credentials", "auth", True),
        (test_http_directory_listing, "http_directory_listing", "misconfiguration", False),
        (test_http_directory_traversal, "http_directory_traversal", "path_traversal", False),
        (test_http_dangerous_methods, "http_dangerous_methods", "misconfiguration", False),
        (test_http_missing_security_headers, "http_missing_sec_headers", "hardening", False),
        (test_http_sensitive_files, "http_sensitive_files", "info_disclosure", False),
        (test_http_open_admin, "http_open_admin", "exposed_interface", False),
        (test_http_verbose_server_header, "http_verbose_server", "fingerprinting", False),
        (test_http_no_auth, "http_no_auth", "auth", False),
    ],

    "ssh": [
        (test_ssh_weak_auth, "ssh_weak_auth", "auth", True),
    ],

    "telnet": [
        (test_telnet_open, "telnet_open", "exposed_service", False),
        (test_ssh_weak_auth, "ssh_weak_auth", "auth", True),
        (test_ssh_root_login, "ssh_root_login", "misconfiguration", True),
        (test_ssh_password_auth_enabled, "ssh_password_auth", "policy", True),
        (test_ssh_old_version, "ssh_old_version", "version", False),
        (test_ssh_weak_crypto, "ssh_weak_crypto", "crypto", False),
        (test_ssh_no_auth_limit, "ssh_no_auth_limit", "bruteforce", True),
    ],

    "mqtt": [
        (test_mqtt_open_access, "mqtt_open_access", "auth", False),
        (test_mqtt_anonymous_publish, "mqtt_anon_publish", "auth", False),
        (test_mqtt_acl_bypass, "mqtt_acl_bypass", "authorization", False),
        (test_mqtt_topic_enum, "mqtt_topic_enum", "info_disclosure", False),
    ],

    "rtsp": [
        (test_rtsp_open, "rtsp_open", "exposed_service", False),
    ],
}
