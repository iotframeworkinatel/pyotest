# Pyotest - IoT Network Vulnerability Scanner

**Pyotest** is a Python-based framework for **scanning and testing IoT device vulnerabilities** across local networks.  
It supports multiple scanning techniques (Nmap, Scapy), tests insecure protocols, and helps map vulnerabilities against the **OWASP IoT Top 10**.

---

## 1. Requirements

### Functional Requirements

- **IoT Security Testing**: Detect weak authentication, insecure APIs, open ports, and missing encryption.
- **Multi-Protocol Support**: MQTT, CoAP, HTTP, Telnet, SSH, etc.
- **Test Automation**: Integration with CI/CD pipelines (GitHub Actions, Jenkins).
- **Containerized Execution**: Run tests in isolated Docker environments.
- **Firmware Testing**: Analyze extracted device firmware.
- **Malicious Traffic Simulation**: Allow brute-force, sniffing, and other network attacks.
- **Detailed Reporting**: Map discovered vulnerabilities with OWASP IoT Top 10 guidelines.

### Non-Functional Requirements

- **Modularity**: Plugin-based architecture for easy extensibility.
- **Ease of Use**: Simple for developers to add new test cases.
- **Scalability**: Support for scanning multiple devices simultaneously.
- **Open Source**: Available on GitHub for public collaboration.

---

## 2. Core Libraries

- [`pytest`](https://docs.pytest.org/): Test framework.
- [`scapy`](https://scapy.readthedocs.io/): Network packet crafting and sniffing.
- [`python-nmap`](https://pypi.org/project/python-nmap/): Nmap port scanning wrapper.
- [`requests`](https://requests.readthedocs.io/): API testing.
- [`binwalk`](https://github.com/ReFirmLabs/binwalk): Firmware analysis.

You can install all dependencies with:

```bash
pip install -r requirements.txt
```

Make sure you also have **Nmap** installed on your system if using Nmap scans:

```bash
# Ubuntu/Debian
sudo apt install nmap

# macOS (Homebrew)
brew install nmap
```

---

## 3. How to Run the Scanner

Navigate to the project root and execute:

```bash
python scanner.py [OPTIONS]
```

Replace `scanner.py` with the correct script filename if needed.

### Available Options

| Option               | Description                                                             | Default                  |
|----------------------|-------------------------------------------------------------------------|---------------------------|
| `-v`, `--verbose`     | Enable verbose logging                                                  | Off                       |
| `-a`, `--all`         | Run **all available** scanning methods                                 | Off                       |
| `-i`, `--interface`   | Network interface to use (e.g., `eth0`, `wlan0`)                        | `eth0`                    |
| `-ip`, `--ip`         | Specific IP address to scan                                             | None                      |
| `-m`, `--mac`         | Specific MAC address to scan                                            | None                      |
| `-r`, `--network`     | Network CIDR block to scan (e.g., `192.168.0.0/24`) or `auto`            | `auto`                    |
| `-s`, `--scans`       | Comma-separated scan types to run (`nmap`, `scapy`)                     | None (requires `-a` or `-s`) |
| `-o`, `--output`      | Output file name to save results                                        | `report.txt`              |
| `-p`, `--ports`       | Extra ports to scan (comma-separated, e.g., `80,443,8080`)               | None                      |

---

## 4. Usage Examples

**Run a full scan using all methods**:

```bash
python scanner.py -a
```

**Scan a specific IP address with Nmap only**:

```bash
python scanner.py -s nmap -ip 192.168.1.10
```

**Scan a specific network and save results to a custom output file**:

```bash
python scanner.py -a -r 192.168.0.0/24 -o scan_results.txt
```

**Scan specific ports using Scapy**:

```bash
python scanner.py -s scapy -p 80,443,8080
```

**Enable verbose mode (debugging output)**:

```bash
python scanner.py -a -v
```

---

## 5. Notes

- If the `--all` flag is used, both Nmap and Scapy scans will run.
- To selectively run scanners, use the `--scans` option with the desired method(s).
- Results will be saved in the file specified by `--output`.
- The tool is designed to be modular and scalable, allowing easy integration of future scanning methods.