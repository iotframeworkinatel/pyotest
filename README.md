# Pyotest - IoT Network Vulnerability Scanner

**Pyotest** is a Python-based framework for **scanning and testing IoT device vulnerabilities** across local networks.  
It supports scanning library (Nmap), tests insecure protocols, and helps map vulnerabilities against the **OWASP IoT Top 10**.

---

## 1. Requirements

### Functional Requirements

- **IoT Security Testing**: Detect weak authentication, insecure APIs, open ports, and missing encryption.
- **Multi-Protocol Support**: MQTT, HTTP, Telnet, SSH, etc.
- **Test Automation**: Integration with CI/CD pipelines (GitHub Actions, Jenkins).
- **Containerized Execution**: Run tests in isolated Docker environments.
- **Detailed Reporting**: Map discovered vulnerabilities.

### Non-Functional Requirements

- **Modularity**: Plugin-based architecture for easy extensibility.
- **Ease of Use**: Simple for developers to add new test cases.
- **Scalability**: Support for scanning multiple devices simultaneously.
- **Open Source**: Available on GitHub for public collaboration.

---

## 2. Core Libraries

- [`python-nmap`](https://pypi.org/project/python-nmap/): Nmap port scanning wrapper.
- [`requests`](https://requests.readthedocs.io/): API testing.
- [`paramiko`](http://www.paramiko.org/): SSH connections.
- [`paho-mqtt`](https://pypi.org/project/paho-mqtt/): MQTT client.

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

Install on windows using the installer from the official Nmap website: [Nmap Download](https://nmap.org/download.html).

---

## 3. How to Run the Scanner

Navigate to the project root and execute:

```bash
python . [OPTIONS]
```

### Available Options

| Option               | Description                                                             | Default                   |
|----------------------|-------------------------------------------------------------------------|---------------------------|
| `-v`, `--verbose`    | Enable verbose logging                                                  | Off                       |
| `-n`, `--network`    | Network CIDR block to scan (e.g., `192.168.0.0/24`, `192.168.0.0-255`)  | `192.168.0.0/24`          |
| `-o`, `--output`     | Output file format (e.g., html, json, csv)                              | None                      |
| `-p`, `--ports`      | Extra ports to scan (comma-separated, e.g., `80,443,8080`)              | None                      |
| `-t`, `--test`       | Run vulnerability tests on discovered devices                           | Off                       |

---

## 4. Usage Examples

**Run a full scan without testing**:

```bash
python . -n 192.168.15.0/24
```

**Run a full scan with vulnerability testing**:

```bash
python . -n 192.168.15.0/24 -t
```

**Run a full scan with vulnerability testing and save results in HTML format**:

```bash
python . -n 192.168.15.0/24 -t -o html
```

**Run a full scan with vulnerability testing and specify extra ports**:

```bash
python . -n 192.168.15.0/24 -p 123,456,7890
```

**Enable verbose mode (debugging output)**:

```bash
python . -v
```

**Run a simulation with Docker**:

```bash
docker-compose up --build 
```
---

## 5. Notes

- Running locally or in a Docker container the results will be saved in the `reports` folder.
- The `docker-compose-localhost.yml` file is configured to run the scanner in a Docker container.

