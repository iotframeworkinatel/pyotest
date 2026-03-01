"""
Simulation Actions — Docker container manipulation functions and vulnerability registries.

Each entry in PATCHABLE_VULNS maps a (container_name, vuln_id) pair to
shell commands that patch or unpatch the vulnerability via `docker exec`.

Each entry in ROTATABLE_CREDS maps a container to credential-rotation commands.

All commands assume execution via container.exec_run() through the Docker socket.
"""
import logging
import time
from typing import Optional

logger = logging.getLogger("simulation.actions")


# ── All 13 IoT device container names ──
IOT_DEVICES = [
    "ftp_anonymous",
    "http_traversal",
    "telnet_insecure",
    "ftp_banner",
    "http_admin_default_creds",
    "http_directory_listing",
    "mqtt_no_auth",
    "ssh_old_banner",
    "ftp_credentials_vuln",
    "coap_vuln",
    "modbus_vuln",
    "http_api_vuln",
    "dns_vuln",
]


# ── Patchable Vulnerabilities Registry ──
# Maps (container_name, vuln_id) → {patch_cmd, unpatch_cmd, needs_restart, description}
#
# patch_cmd: shell command(s) to remove/disable the vulnerability
# unpatch_cmd: shell command(s) to restore the vulnerability
# needs_restart: whether the container needs restart after patching
# description: human-readable explanation of what changes

PATCHABLE_VULNS = {
    # ── HTTP Traversal (Apache httpd) ──
    ("http_traversal", "http_sensitive_files"): {
        "patch": (
            "mv /usr/local/apache2/htdocs/.env /usr/local/apache2/htdocs/.env.sim_hidden 2>/dev/null; "
            "mv /usr/local/apache2/htdocs/.env.bak /usr/local/apache2/htdocs/.env.bak.sim_hidden 2>/dev/null; "
            "mv /usr/local/apache2/htdocs/backup.sql /usr/local/apache2/htdocs/backup.sql.sim_hidden 2>/dev/null"
        ),
        "unpatch": (
            "mv /usr/local/apache2/htdocs/.env.sim_hidden /usr/local/apache2/htdocs/.env 2>/dev/null; "
            "mv /usr/local/apache2/htdocs/.env.bak.sim_hidden /usr/local/apache2/htdocs/.env.bak 2>/dev/null; "
            "mv /usr/local/apache2/htdocs/backup.sql.sim_hidden /usr/local/apache2/htdocs/backup.sql 2>/dev/null"
        ),
        "needs_restart": False,
        "description": "Hide sensitive files (.env, .env.bak, backup.sql) from web root",
    },
    ("http_traversal", "http_dav_enabled"): {
        "patch": (
            "sed -i 's/Dav On/Dav Off/' /usr/local/apache2/conf/extra/httpd-vuln.conf"
        ),
        "unpatch": (
            "sed -i 's/Dav Off/Dav On/' /usr/local/apache2/conf/extra/httpd-vuln.conf"
        ),
        "needs_restart": True,
        "description": "Disable WebDAV (PUT/DELETE methods)",
    },
    ("http_traversal", "http_trace_enabled"): {
        "patch": (
            "sed -i 's/TraceEnable on/TraceEnable off/' /usr/local/apache2/conf/extra/httpd-vuln.conf"
        ),
        "unpatch": (
            "sed -i 's/TraceEnable off/TraceEnable on/' /usr/local/apache2/conf/extra/httpd-vuln.conf"
        ),
        "needs_restart": True,
        "description": "Disable HTTP TRACE method (XST mitigation)",
    },

    # ── MQTT No Auth (Mosquitto) ──
    ("mqtt_no_auth", "mqtt_open_access"): {
        "patch": (
            "sed -i 's/allow_anonymous true/allow_anonymous false/' /mosquitto/config/mosquitto.conf"
        ),
        "unpatch": (
            "sed -i 's/allow_anonymous false/allow_anonymous true/' /mosquitto/config/mosquitto.conf"
        ),
        "needs_restart": True,
        "description": "Disable anonymous MQTT access",
    },

    # ── FTP Anonymous (vsftpd) ──
    ("ftp_anonymous", "ftp_anonymous_login"): {
        "patch": (
            "sh -c 'echo anonymous_enable=NO >> /etc/vsftpd/vsftpd.conf'"
        ),
        "unpatch": (
            "sed -i '/anonymous_enable=NO/d' /etc/vsftpd/vsftpd.conf"
        ),
        "needs_restart": True,
        "description": "Disable anonymous FTP login",
    },

    # ── HTTP Directory Listing (Apache httpd) ──
    ("http_directory_listing", "http_dir_listing"): {
        "patch": (
            "sed -i 's/Options +Indexes/Options -Indexes/' /usr/local/apache2/conf/conf.d/directory-listing.conf"
        ),
        "unpatch": (
            "sed -i 's/Options -Indexes/Options +Indexes/' /usr/local/apache2/conf/conf.d/directory-listing.conf"
        ),
        "needs_restart": True,
        "description": "Disable directory listing in Apache",
    },

    # ── HTTP Admin Panel (Flask) ──
    ("http_admin_default_creds", "http_admin_unprotected"): {
        "patch": (
            "sed -i \"s|@app.route('/admin')|@app.route('/admin_SIMOFF')|\" /app/app.py"
        ),
        "unpatch": (
            "sed -i \"s|@app.route('/admin_SIMOFF')|@app.route('/admin')|\" /app/app.py"
        ),
        "needs_restart": True,
        "description": "Disable unprotected admin endpoint",
    },
    ("http_admin_default_creds", "http_cors_wildcard"): {
        "patch": (
            "sed -i \"s/Access-Control-Allow-Origin', '\\*'/Access-Control-Allow-Origin', 'https:\\/\\/admin.local'/\" /app/app.py"
        ),
        "unpatch": (
            "sed -i \"s/Access-Control-Allow-Origin', 'https:\\/\\/admin.local'/Access-Control-Allow-Origin', '\\*'/\" /app/app.py"
        ),
        "needs_restart": True,
        "description": "Restrict CORS from wildcard to specific origin",
    },

    # ── DNS Open Resolver (dnsmasq) ──
    ("dns_vuln", "dns_open_resolver"): {
        "patch": (
            "sed -i 's/listen-address=0.0.0.0/listen-address=127.0.0.1/' /etc/dnsmasq.conf"
        ),
        "unpatch": (
            "sed -i 's/listen-address=127.0.0.1/listen-address=0.0.0.0/' /etc/dnsmasq.conf"
        ),
        "needs_restart": True,
        "description": "Bind DNS to localhost only (close open resolver)",
    },
    ("dns_vuln", "dns_zone_transfer"): {
        "patch": (
            "sed -i 's/log-queries/# log-queries/' /etc/dnsmasq.conf; "
            "sed -i 's/no-dnssec-check/# no-dnssec-check/' /etc/dnsmasq.conf"
        ),
        "unpatch": (
            "sed -i 's/# log-queries/log-queries/' /etc/dnsmasq.conf; "
            "sed -i 's/# no-dnssec-check/no-dnssec-check/' /etc/dnsmasq.conf"
        ),
        "needs_restart": True,
        "description": "Disable query logging and enable DNSSEC validation",
    },

    # ── SSH Old Banner ──
    ("ssh_old_banner", "ssh_root_login"): {
        "patch": (
            "sed -i 's/PermitRootLogin yes/PermitRootLogin no/' /etc/ssh/sshd_config"
        ),
        "unpatch": (
            "sed -i 's/PermitRootLogin no/PermitRootLogin yes/' /etc/ssh/sshd_config"
        ),
        "needs_restart": True,
        "description": "Disable SSH root login",
    },

    # ── HTTP API Vuln (Python BaseHTTPRequestHandler) ──
    ("http_api_vuln", "http_api_debug"): {
        "patch": (
            "sed -i 's/DEBUG_ENABLED = True/DEBUG_ENABLED = False/' /server.py"
        ),
        "unpatch": (
            "sed -i 's/DEBUG_ENABLED = False/DEBUG_ENABLED = True/' /server.py"
        ),
        "needs_restart": True,
        "description": "Disable debug mode (hide /api/debug endpoint data)",
    },
    ("http_api_vuln", "http_api_env_exposed"): {
        "patch": "mv /.env /.env.sim_hidden 2>/dev/null || true",
        "unpatch": "mv /.env.sim_hidden /.env 2>/dev/null || true",
        "needs_restart": False,
        "description": "Hide .env file from web access",
    },

    # ── CoAP Vuln (Python aiocoap) ──
    ("coap_vuln", "coap_hidden_resources"): {
        "patch": (
            "sed -i \"s|root.add_resource.*'secret'|# SIM_PATCHED: root.add_resource_secret|\" /server.py"
        ),
        "unpatch": (
            "sed -i 's/# SIM_PATCHED: root.add_resource_secret/root.add_resource((\"secret\",), SecretResource())/' /server.py"
        ),
        "needs_restart": True,
        "description": "Remove hidden /secret CoAP resource",
    },
    ("coap_vuln", "coap_writable_config"): {
        "patch": (
            "sed -i 's/async def render_put/async def render_put_SIMOFF/' /server.py; "
            "sed -i 's/async def render_delete/async def render_delete_SIMOFF/' /server.py"
        ),
        "unpatch": (
            "sed -i 's/async def render_put_SIMOFF/async def render_put/' /server.py; "
            "sed -i 's/async def render_delete_SIMOFF/async def render_delete/' /server.py"
        ),
        "needs_restart": True,
        "description": "Disable PUT/DELETE on CoAP config resource",
    },
}


# ── Rotatable Credentials Registry ──
# Maps container_name → {users, rotate_cmd_template, default_password}
#
# rotate_cmd_template: shell command with {new_pass} placeholder
# default_password: the original password to restore on regression

ROTATABLE_CREDS = {
    "telnet_insecure": {
        "users": ["admin", "root"],
        "rotate_cmd": "echo '{user}:{new_pass}' | chpasswd",
        "default_password": "admin",
        "description": "Rotate Telnet user passwords",
    },
    "http_admin_default_creds": {
        "users": ["admin"],
        "rotate_cmd": (
            "sed -i \"s/ADMIN_PASS = .*/ADMIN_PASS = '{new_pass}'/\" /app/app.py"
        ),
        "default_password": "admin",
        "needs_restart": True,
        "description": "Change Flask admin panel password",
    },
    "ftp_anonymous": {
        "users": ["admin"],
        "rotate_cmd": "echo '{new_pass}' | passwd --stdin {user} 2>/dev/null || echo '{user}:{new_pass}' | chpasswd",
        "default_password": "admin",
        "description": "Change FTP user password",
    },
}


# ── Docker Manipulation Functions ──

def stop_container(docker_client, container_name: str) -> bool:
    """Stop a Docker container (simulates service outage).

    Args:
        docker_client: Docker client instance.
        container_name: Name of the container to stop.

    Returns:
        True if successfully stopped, False otherwise.
    """
    try:
        container = docker_client.containers.get(container_name)
        container.stop(timeout=5)
        logger.info(f"[Simulation] Stopped container: {container_name}")
        return True
    except Exception as e:
        logger.warning(f"[Simulation] Failed to stop {container_name}: {e}")
        return False


def start_container(docker_client, container_name: str) -> bool:
    """Start a stopped Docker container (restore from outage).

    Args:
        docker_client: Docker client instance.
        container_name: Name of the container to start.

    Returns:
        True if successfully started, False otherwise.
    """
    try:
        container = docker_client.containers.get(container_name)
        container.start()
        logger.info(f"[Simulation] Started container: {container_name}")
        return True
    except Exception as e:
        logger.warning(f"[Simulation] Failed to start {container_name}: {e}")
        return False


def restart_container(docker_client, container_name: str) -> bool:
    """Restart a container to apply config changes.

    Args:
        docker_client: Docker client instance.
        container_name: Name of the container to restart.

    Returns:
        True if successfully restarted, False otherwise.
    """
    try:
        container = docker_client.containers.get(container_name)
        container.restart(timeout=5)
        logger.info(f"[Simulation] Restarted container: {container_name}")
        return True
    except Exception as e:
        logger.warning(f"[Simulation] Failed to restart {container_name}: {e}")
        return False


def exec_in_container(docker_client, container_name: str, cmd: str) -> tuple[bool, str]:
    """Execute a shell command inside a running container.

    Args:
        docker_client: Docker client instance.
        container_name: Name of the container.
        cmd: Shell command to execute.

    Returns:
        Tuple of (success: bool, output: str).
    """
    try:
        container = docker_client.containers.get(container_name)
        exit_code, output = container.exec_run(
            ["sh", "-c", cmd],
            demux=True,
        )
        stdout = (output[0] or b"").decode("utf-8", errors="replace").strip()
        stderr = (output[1] or b"").decode("utf-8", errors="replace").strip()
        combined = f"{stdout}\n{stderr}".strip()

        success = exit_code == 0
        if success:
            logger.debug(f"[Simulation] exec {container_name}: {cmd[:60]}... → OK")
        else:
            logger.warning(
                f"[Simulation] exec {container_name}: {cmd[:60]}... → "
                f"exit={exit_code} {combined[:100]}"
            )
        return success, combined
    except Exception as e:
        logger.warning(f"[Simulation] exec failed on {container_name}: {e}")
        return False, str(e)


def apply_patch(docker_client, container_name: str, vuln_id: str) -> bool:
    """Apply a vulnerability patch to a container.

    Args:
        docker_client: Docker client instance.
        container_name: Name of the container.
        vuln_id: Vulnerability identifier from PATCHABLE_VULNS.

    Returns:
        True if patch was applied successfully.
    """
    key = (container_name, vuln_id)
    if key not in PATCHABLE_VULNS:
        logger.warning(f"[Simulation] Unknown patchable vuln: {key}")
        return False

    entry = PATCHABLE_VULNS[key]
    success, output = exec_in_container(docker_client, container_name, entry["patch"])

    if success and entry.get("needs_restart", False):
        restart_container(docker_client, container_name)
        # Brief pause for service to come back up
        time.sleep(1)

    if success:
        logger.info(f"[Simulation] Patched {container_name}/{vuln_id}: {entry['description']}")
    return success


def apply_unpatch(docker_client, container_name: str, vuln_id: str) -> bool:
    """Reverse a vulnerability patch (simulate regression/rollback).

    Args:
        docker_client: Docker client instance.
        container_name: Name of the container.
        vuln_id: Vulnerability identifier from PATCHABLE_VULNS.

    Returns:
        True if unpatch was applied successfully.
    """
    key = (container_name, vuln_id)
    if key not in PATCHABLE_VULNS:
        logger.warning(f"[Simulation] Unknown patchable vuln: {key}")
        return False

    entry = PATCHABLE_VULNS[key]
    success, output = exec_in_container(docker_client, container_name, entry["unpatch"])

    if success and entry.get("needs_restart", False):
        restart_container(docker_client, container_name)
        time.sleep(1)

    if success:
        logger.info(f"[Simulation] Unpatched {container_name}/{vuln_id} (regression)")
    return success


def rotate_credentials(docker_client, container_name: str, new_password: str) -> bool:
    """Rotate credentials on a container.

    Args:
        docker_client: Docker client instance.
        container_name: Name of the container.
        new_password: New password to set.

    Returns:
        True if credentials were rotated successfully.
    """
    if container_name not in ROTATABLE_CREDS:
        logger.warning(f"[Simulation] No rotatable creds for: {container_name}")
        return False

    entry = ROTATABLE_CREDS[container_name]
    all_ok = True

    for user in entry["users"]:
        cmd = entry["rotate_cmd"].format(user=user, new_pass=new_password)
        success, output = exec_in_container(docker_client, container_name, cmd)
        if not success:
            all_ok = False

    if all_ok and entry.get("needs_restart", False):
        restart_container(docker_client, container_name)
        time.sleep(1)

    if all_ok:
        logger.info(
            f"[Simulation] Rotated credentials on {container_name} "
            f"(users: {entry['users']})"
        )
    return all_ok


def reset_credentials(docker_client, container_name: str) -> bool:
    """Reset credentials to default (for cleanup/restore).

    Args:
        docker_client: Docker client instance.
        container_name: Name of the container.

    Returns:
        True if credentials were reset successfully.
    """
    if container_name not in ROTATABLE_CREDS:
        return False

    entry = ROTATABLE_CREDS[container_name]
    default_pass = entry["default_password"]
    return rotate_credentials(docker_client, container_name, default_pass)
