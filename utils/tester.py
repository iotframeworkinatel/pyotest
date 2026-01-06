from vulnerability_tester import *
import logging
from utils.metrics import save_metrics
import time


def general_tester(iot_devices, args):
    """
    General vulnerability tester for IoT devices.
    Static baseline for comparison with AutoML.
    """

    start = time.time()

    # =========================
    # Métricas estáticas
    # =========================
    static_tests_executed = 0
    static_vulns_found = 0

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    logging.info("Starting static vulnerability tests...")

    for d in iot_devices:
        logging.info(f"Testing device {d.ip} with ports {d.ports}...")

        for port in d.ports:

            # FTP
            if port == 21:
                static_tests_executed += 1
                if test_ftp_anonymous_login(d.ip, port):
                    d.vulnerabilities.append("Anonymous FTP login allowed")
                    static_vulns_found += 1

            # HTTP
            elif port == 80:
                static_tests_executed += 1
                if test_http_default_credentials(d.ip, port, args):
                    d.vulnerabilities.append("Default HTTP credentials accepted")
                    static_vulns_found += 1

                static_tests_executed += 1
                if test_http_directory_listing(d.ip, port):
                    d.vulnerabilities.append("Directory listing enabled")
                    static_vulns_found += 1

                static_tests_executed += 1
                if test_http_directory_traversal(d.ip, port):
                    d.vulnerabilities.append("Directory traversal vulnerability found")
                    static_vulns_found += 1

            # # Telnet
            # elif port == 23:
            #     static_tests_executed += 1
            #     if test_telnet_open(d.ip, port):
            #         d.vulnerabilities.append("Telnet open and accessible")
            #         static_vulns_found += 1
            #
            # # SSH
            # elif port == 22:
            #     static_tests_executed += 1
            #     if test_ssh_weak_auth(d.ip, port, timeout=0.1, args=args):
            #         d.vulnerabilities.append("SSH weak credentials allowed")
            #         static_vulns_found += 1
            #
            # # MQTT
            # elif port == 1883:
            #     static_tests_executed += 1
            #     if test_mqtt_open_access(d.ip, port):
            #         d.vulnerabilities.append("MQTT broker allows anonymous access")
            #         static_vulns_found += 1
            #
            # # RTSP
            # elif port == 554:
            #     static_tests_executed += 1
            #     rtsp_script_output = rtsp_brute_force(
            #         ip=d.ip,
            #         port=port,
            #         args=args,
            #         wordlist_path="./vulnerability_tester/rtsp-urls.txt"
            #     )
            #     if rtsp_script_output:
            #         d.vulnerabilities.append("RTSP URL brute force output found")
            #         static_vulns_found += 1
            #
            #     static_tests_executed += 1
            #     if test_rtsp_open(d.ip, port):
            #         d.vulnerabilities.append("RTSP open and accessible")
            #         static_vulns_found += 1
            #
            # # Banner grabbing (sempre conta)
            # static_tests_executed += 1
            # if grab_banner(d.ip, port):
            #     d.vulnerabilities.append("Banner grabbed")
            #     static_vulns_found += 1

        logging.info(f"Device {d.ip} vulnerabilities: {d.vulnerabilities}")

    # =========================
    # Exportação das métricas
    # =========================
    duration = time.time() - start

    save_metrics({
        "mode": "static",
        "devices": len(iot_devices),
        "tests_generated": static_tests_executed,
        "tests_executed": static_tests_executed,
        "vulns_detected": static_vulns_found,
        "false_positives": 0,  # assumido (baseline)
        "exec_time_sec": int(duration * 1000)
    })

    return iot_devices
