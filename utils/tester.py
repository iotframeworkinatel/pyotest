from vulnerability_tester import *
import logging

def general_tester(iot_devices, args):
    """
    General vulnerability tester for IoT devices.
    This function tests various vulnerabilities on the provided IoT devices.
    """

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
    else:
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    logging.info("Starting vulnerability tests...")

    # Loop through each device and test for vulnerabilities

    for d in iot_devices:
        logging.info(f"Testing device {d.ip} with ports {d.ports}...")

        for port in d.ports:
            # FTP
            if port == 21:
                logging.debug(f"Testing anonymous FTP on {d.ip}...")
                if test_ftp_anonymous_login(d.ip, port):
                    logging.debug("Anonymous FTP login allowed.")
                    d.vulnerabilities.append("Anonymous FTP login allowed")
                else:
                    logging.debug("Anonymous FTP login not allowed.")


            # HTTP
            elif port == 80:
                logging.debug(f"Testing default credentials on HTTP service at {d.ip}...")
                if test_http_default_credentials(d.ip, port, args):
                    logging.debug("Default HTTP credentials accepted.")
                    d.vulnerabilities.append("Default HTTP credentials accepted")
                else:
                    logging.debug("Default HTTP credentials rejected.")

                logging.debug(f"Testing directory listing on {d.ip}...")
                if test_http_directory_listing(d.ip, port):
                    logging.debug("Directory listing enabled.")
                    d.vulnerabilities.append("Directory listing enabled")
                else:
                    logging.debug("Directory listing disabled.")

                logging.debug(f"Testing directory traversal on {d.ip}...")
                if test_http_directory_traversal(d.ip, port):
                    logging.debug("Directory traversal vulnerability found.")
                    d.vulnerabilities.append("Directory traversal vulnerability found")
                else:
                    logging.debug("No traversal vulnerability detected.")

            # Telnet
            elif port == 23:
                logging.debug(f"Testing open Telnet on {d.ip}...")
                if test_telnet_open(d.ip, port):
                    logging.debug("Telnet open and accessible.")
                    d.vulnerabilities.append("Telnet open and accessible")
                else:
                    logging.debug("Telnet not accessible.")

            # SSH
            elif port == 22:
                logging.debug(f"Testing SSH weak auth on {d.ip}...")
                if test_ssh_weak_auth(d.ip, port, timeout=0.1, args=args):
                    logging.debug("SSH weak credentials allowed.")
                    d.vulnerabilities.append("SSH weak credentials allowed")
                else:
                    logging.debug("SSH credentials blocked.")

            # MQTT
            elif port == 1883:
                logging.debug(f"Testing open MQTT broker on {d.ip}...")
                if test_mqtt_open_access(d.ip, port):
                    logging.debug("MQTT broker allows anonymous access.")
                    d.vulnerabilities.append("MQTT broker allows anonymous access")
                else:
                    logging.debug("MQTT broker is restricted or unavailable.")

            # RTSP
            elif port == 554:
                logging.debug(f"Running RTSP URL brute force on {d.ip}...")
                rtsp_script_output = rtsp_brute_force(ip=d.ip, port=port, args=args, wordlist_path="./vulnerability_tester/rtsp-urls.txt")
                if rtsp_script_output != []:
                    logging.debug("RTSP URL brute force output:")
                    logging.debug(rtsp_script_output)
                    d.vulnerabilities.append(f"RTSP URL brute force output found: {rtsp_script_output}")
                else:
                    logging.debug(f"No RTSP URL brute force was successful on {d.ip}.")

                logging.debug(f"Testing RTSP open on {d.ip}...")
                if test_rtsp_open(d.ip, port):
                    logging.debug("RTSP open and accessible.")
                    d.vulnerabilities.append("RTSP open and accessible")
                else:
                    logging.debug("RTSP not accessible.")

            # Generic banner grabbing (can keep last)
            logging.debug(f"Grabbing banner from {d.ip}:{port}...")
            if grab_banner(d.ip, port):
                logging.debug("Banner grabbed.")
                d.vulnerabilities.append("Banner grabbed")
            else:
                logging.debug("No banner received.")
        logging.info(f"Device {d.ip} vulnerabilities: {d.vulnerabilities}")
    return iot_devices