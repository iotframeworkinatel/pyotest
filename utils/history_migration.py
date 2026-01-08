import json
from pathlib import Path

HISTORY_FILE = Path("auto_ml_history/history.json")
BACKUP_FILE = Path("auto_ml_history/history.backup.json")

REQUIRED_KEYS = {
    "test_name",
    "test_type",
    "port_count",
    "has_ftp",
    "has_ssh",
    "has_telnet",
    "has_http",
    "has_mqtt",
    "test_useful",
    "vuln_found",
}


def infer_test_type(test_name: str) -> str:
    name = test_name.upper()

    if "FTP" in name:
        return "FTP"
    if "SSH" in name:
        return "SSH"
    if "TELNET" in name:
        return "TELNET"
    if "HTTP" in name:
        return "HTTP"
    if "MQTT" in name:
        return "MQTT"

    return "UNKNOWN"


def needs_migration(entry: dict) -> bool:
    if not isinstance(entry, dict):
        return True

    missing = REQUIRED_KEYS - entry.keys()
    return len(missing) > 0


def migrate_history_if_needed():
    if not HISTORY_FILE.exists():
        return

    raw = json.loads(HISTORY_FILE.read_text())

    if not isinstance(raw, list):
        print("[HISTORY] Formato inválido, ignorando")
        return

    if not any(needs_migration(e) for e in raw):
        # Histórico já está no formato novo
        return

    print("[HISTORY] Migração necessária, iniciando...")

    HISTORY_FILE.rename(BACKUP_FILE)

    migrated = []

    for entry in raw:
        if not isinstance(entry, dict):
            continue

        test_name = entry.get("test_name", "UNKNOWN")

        migrated.append({
            "test_name": test_name,
            "test_type": entry.get("test_type") or infer_test_type(test_name),
            "port_count": int(entry.get("port_count", 1)),
            "has_ftp": bool(entry.get("has_ftp", False)),
            "has_ssh": bool(entry.get("has_ssh", False)),
            "has_telnet": bool(entry.get("has_telnet", False)),
            "has_http": bool(entry.get("has_http", False)),
            "has_mqtt": bool(entry.get("has_mqtt", False)),
            "test_useful": int(entry.get("test_useful", 0)),
            "vuln_found": entry.get("vuln_found"),
        })

    HISTORY_FILE.write_text(json.dumps(migrated, indent=2))
    print(f"[HISTORY] Migração concluída. Backup em {BACKUP_FILE}")
