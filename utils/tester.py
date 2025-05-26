from vulnerability_tester import *

def general_tester(iot_devices):
    """
    General vulnerability tester for IoT devices.
    This function tests various vulnerabilities on the provided IoT devices.
    """
    print("\n[+] Starting vulnerability tests...\n")

    # Loop through each device and test for vulnerabilities

    for d in iot_devices:
        print(f"\n[+] Testing device {d.ip} with ports {d.ports}...\n")

        for port in d.ports:
            # FTP
            if port == 21:
                print(f"[*] Testing anonymous FTP on {d.ip}...")
                if test_ftp_anonymous_login(d.ip, port):
                    print("[✔] Anonymous FTP login allowed.")
                    d.vulnerabilities.append("Anonymous FTP login allowed")
                else:
                    print("[✘] Anonymous FTP login not allowed.")

                print(f"[*] Grabbing FTP banner on {d.ip}...")
                if test_ftp_banner_grabbing(d.ip, port):
                    print("[✔] FTP banner exposed.")
                    d.vulnerabilities.append("FTP banner exposed")
                else:
                    print("[✘] No FTP banner found.")

            # HTTP
            elif port == 80:
                print(f"[*] Testing default credentials on HTTP service at {d.ip}...")
                if test_http_default_credentials(d.ip, port):
                    print("[✔] Default HTTP credentials accepted.")
                    d.vulnerabilities.append("Default HTTP credentials accepted")
                else:
                    print("[✘] Default HTTP credentials rejected.")

                print(f"[*] Testing directory listing on {d.ip}...")
                if test_http_directory_listing(d.ip, port):
                    print("[✔] Directory listing enabled.")
                    d.vulnerabilities.append("Directory listing enabled")
                else:
                    print("[✘] Directory listing disabled.")

                print(f"[*] Testing directory traversal on {d.ip}...")
                if test_http_directory_traversal(d.ip, port):
                    print("[✔] Directory traversal vulnerability found.")
                    d.vulnerabilities.append("Directory traversal vulnerability found")
                else:
                    print("[✘] No traversal vulnerability detected.")

            # Telnet
            elif port == 23:
                print(f"[*] Testing open Telnet on {d.ip}...")
                if test_telnet_open(d.ip, port):
                    print("[✔] Telnet open and accessible.")
                    d.vulnerabilities.append("Telnet open and accessible")
                else:
                    print("[✘] Telnet not accessible.")

            # SSH
            elif port == 22:
                print(f"[*] Testing SSH weak auth on {d.ip}...")
                if test_ssh_weak_auth(d.ip):
                    print("[✔] SSH weak credentials allowed.")
                    d.vulnerabilities.append("SSH weak credentials allowed")
                else:
                    print("[✘] SSH credentials blocked.")

            # MQTT
            elif port == 1883:
                print(f"[*] Testing open MQTT broker on {d.ip}...")
                if test_mqtt_open_access(d.ip, port):
                    print("[✔] MQTT broker allows anonymous access.")
                    d.vulnerabilities.append("MQTT broker allows anonymous access")
                else:
                    print("[✘] MQTT broker is restricted or unavailable.")

            # RTSP
            elif port == 554:
                print(f"[*] Running RTSP URL brute force on {d.ip}...")
                rtsp_script_output = rtsp_brute_force(d.ip)
                if rtsp_script_output != []:
                    print("[✔] RTSP URL brute force output:")
                    print(rtsp_script_output)
                    d.vulnerabilities.append(f"RTSP URL brute force output found: {rtsp_script_output}")
                else:
                    print(f"[✘] No RTSP URL brute force was successful on {d.ip}.")

                print(f"[*] Testing RTSP open on {d.ip}...")
                if test_rtsp_open(d.ip, port):
                    print("[✔] RTSP open and accessible.")
                    d.vulnerabilities.append("RTSP open and accessible")
                else:
                    print("[✘] RTSP not accessible.")

            # Generic banner grabbing (can keep last)
            print(f"[*] Grabbing banner from {d.ip}:{port}...")
            if grab_banner(d.ip, port):
                print("[✔] Banner grabbed.")
                d.vulnerabilities.append("Banner grabbed")
            else:
                print("[✘] No banner received.")
        print(f"\n[+] Device {d.ip} vulnerabilities: {d.vulnerabilities}")
    return iot_devices