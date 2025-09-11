# Pyotest - IoT Network Vulnerability Scanner

**Pyotest** is a Python-based framework for **scanning and testing IoT device vulnerabilities** across local networks.  
It supports scanning library (Nmap), tests insecure protocols, and helps map vulnerabilities against the **OWASP IoT Top 10**.

---

# 1. System Overview

### Functional overview
Pyotest scans local networks for IoT devices, identifies open ports, and performs vulnerability tests.

- **IoT Security Testing**: Detect weak authentication, insecure APIs, open ports, and missing encryption.
- **Multi-Protocol Support**: MQTT, HTTP, Telnet, SSH, etc.
- **Test Automation**: Integration with CI/CD pipelines (GitHub Actions, Jenkins).
- **Containerized Execution**: Run tests in isolated Docker environments.
- **Detailed Reporting**: Export results in HTML, JSON, and CSV format.
- **Possible to use AutoML for anomaly detection and test case generation for high risk scenarios** (future feature).

### Non-Functional overview

- **Modularity**: Plugin-based architecture for easy extensibility.
- **Ease of Use**: Simple for developers to add new test cases.
- **Scalability**: Support for scanning multiple devices simultaneously.
- **Open Source**: Available on GitHub for public collaboration.

---

# 2. Core Libraries

- [`python-nmap`](https://pypi.org/project/python-nmap/): Nmap port scanning wrapper.
- [`requests`](https://requests.readthedocs.io/): API testing.
- [`paramiko`](http://www.paramiko.org/): SSH connections.
- [`h2o`](https://h2o.ai/platform/h2o-automl/): h2o AutoML library for anomaly detection (future feature).
- [`pandas`](https://pandas.pydata.org/): pandas data analysis library.
- [`scikit-learn`](https://scikit-learn.org/stable/): scikit-learn machine learning library (future feature).

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

Make sure you also have **h2o** installed on your system if using h2o automl feature:

```bash
# Ubuntu/Debian
sudo apt install h2o

# macOS (Homebrew)
brew install h2o
```
---

# 3. How to Run the Scanner

Navigate to the project root and execute:

```bash
python . [OPTIONS]
```

### Available Options

| Option             | Description                                                            | Default                   |
|--------------------|------------------------------------------------------------------------|---------------------------|
| `-v`, `--verbose`  | Enable verbose logging                                                 | Off                       |
| `-n`, `--network`  | Network CIDR block to scan (e.g., `192.168.0.0/24`, `192.168.0.0-255`) | `192.168.0.0/24`          |
| `-o`, `--output`   | Output file format (e.g., `html`,`json`,`csv`)                         | None                      |
| `-p`, `--ports`    | Extra ports to scan (comma-separated, e.g., `80,443,8080`)             | None                      |
| `-t`, `--test`     | Run vulnerability tests on discovered devices                          | Off                       |
| `-aml`, `--automl` | Run AutoML to generate test cases for high risk scenarios              | Off                       |

---

# 4. Usage Examples

**Run a full scan without testing**:

```bash
# The scanner will scan the network for devices and open ports and show the results in the terminal.
python . -n 192.168.15.0/24
```

**Run a full scan with vulnerability testing**:

```bash
# The scanner will scan the network for devices, open ports, and run vulnerability tests on discovered devices.
python . -n 192.168.15.0/24 -t
```

**Run a full scan with vulnerability testing and save results in HTML format**:

```bash
# The scanner will scan the network for devices, open ports, run vulnerability tests, and save the results in HTML format.
python . -n 192.168.15.0/24 -t -o html
```

**Run a full scan with vulnerability testing and specify extra ports**:

```bash
# The scanner will scan the network for devices with additional specified ports.
python . -n 192.168.15.0/24 -p 123,456,7890
```

**Enable verbose mode (debugging output)**:

```bash
# The scanner will run in verbose mode, providing detailed output in the terminal.
python . -n 192.168.15.0/24 -v 
```

## 5. Running with Docker - Simulation

**Run a simulation with Docker**:

You must have Docker installed on your system.

Docker Installation instructions can be found here: [Docker Installation](https://docs.docker.com/get-docker/).

```bash
docker-compose up --build 
```

- The scanner will run a simulated environment with a mock IoT device and perform vulnerability tests.
- The results will be saved in the `reports` folder in the project root.
---


## 6. Contributing
We welcome contributions! Please follow these steps:

1. Fork the repository.
2. Create a new branch: `git checkout -b my-branch`.
3. Make your changes.
4. Commit your changes: `git commit -am "Add my changes"`.
5. Push your branch: `git push origin my-branch`.
6. Create a pull request.