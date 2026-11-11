# -*- coding: utf-8 -*-
import os
import sys
import time
import json
import requests
from datetime import datetime
from urllib.parse import urlparse

# -----------------------------
# RUTAS
# -----------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
NOTB_DIR = os.path.join(BASE_DIR, "NOTB")
CFG_FILE = os.path.join(BASE_DIR, "config_tb.json")
LEGACY_CFG_FILE = os.path.join(BASE_DIR, "tb_config.json")

# -----------------------------
# CONFIG POR DEFECTO
# -----------------------------
DEFAULT_CFG = {
    "url": "https://thingsboard.cloud",
    "token": "ACCESS_TOKEN_DEL_DISPOSITIVO",
    "scan_interval_sec": 30,
    "cfg_retry_sec": 10
}

# -----------------------------
# CONFIG
# -----------------------------
def migrate_legacy_config():
    """Migra tb_config.json (nombre antiguo) a config_tb.json."""
    if os.path.exists(CFG_FILE) or not os.path.exists(LEGACY_CFG_FILE):
        return

    try:
        os.replace(LEGACY_CFG_FILE, CFG_FILE)
        print("?? tb_config.json migrado a config_tb.json")
    except OSError as e:
        print(f"?? No se pudo migrar tb_config.json: {e}")


def load_or_create_config():
    cfg_changed = False

    migrate_legacy_config()

    if not os.path.exists(CFG_FILE):
        cfg = DEFAULT_CFG.copy()
        cfg_changed = True
        print("?? config_tb.json creado con valores por defecto")
    else:
        try:
            with open(CFG_FILE, "r") as f:
                cfg = json.load(f)
        except Exception as e:
            print(f"?? Error leyendo config_tb.json: {e}")
            cfg = DEFAULT_CFG.copy()
            cfg_changed = True

    # Completar claves faltantes
    for k, v in DEFAULT_CFG.items():
        if k not in cfg:
            cfg[k] = v
            cfg_changed = True

    if cfg_changed:
        with open(CFG_FILE, "w") as f:
            json.dump(cfg, f, indent=4)

    return cfg


def config_is_valid(cfg):
    url = str(cfg.get("url", "")).strip()
    token = str(cfg.get("token", "")).strip()

    parsed_url = urlparse(url)
    if parsed_url.scheme not in ("http", "https") or not parsed_url.netloc:
        return False

    if not token or token == DEFAULT_CFG["token"]:
        return False

    try:
        if int(cfg.get("scan_interval_sec", 0)) <= 0:
            return False
        if int(cfg.get("cfg_retry_sec", 0)) <= 0:
            return False
    except (TypeError, ValueError):
        return False

    return True

# -----------------------------
# PARSEO Y ENVIO
# -----------------------------
def parse_line(line):
    parts = line.strip().split(",")

    if len(parts) < 14:
        return None

    _, date_str, time_str, mac, \
    pv_v, pv_i, pv_p, \
    bat_v, bat_i, bat_p, \
    load_v, load_i, load_p, \
    qod = parts

    dt = datetime.strptime(
        f"{date_str} {time_str}",
        "%d/%m/%y %H:%M:%S"
    )
    ts = int(dt.timestamp() * 1000)

    data = {
        "pv_v": float(pv_v),
        "pv_i": float(pv_i),
        "pv_pwr": float(pv_p),
        "bat_v": float(bat_v),
        "bat_i": float(bat_i),
        "bat_pwr": float(bat_p),
        "load_v": float(load_v),
        "load_i": float(load_i),
        "load_pwr": float(load_p),
        "qod": float(qod)
    }

    return ts, data


def send_to_tb(tb_url, token, ts, data):
    url = f"{tb_url}/api/v1/{token}/telemetry"
    payload = {
        "ts": ts,
        "values": data
    }
    r = requests.post(url, json=payload, timeout=5)
    return r.status_code == 200

# -----------------------------
# MODO DE VALIDACIÓN (systemd ExecCondition)
# -----------------------------
if "--check-config" in sys.argv[1:]:
    cfg = load_or_create_config()
    if config_is_valid(cfg):
        print("Configuración válida")
        sys.exit(0)

    print(
        "Configuración no válida: define una URL http(s) y un token real "
        f"en {CFG_FILE}"
    )
    sys.exit(1)

# -----------------------------
# LOOP PRINCIPAL
# -----------------------------
print("?? Enviador NOTB ? ThingsBoard iniciado")

while True:
    cfg = load_or_create_config()

    SCAN_INTERVAL_SEC = int(cfg["scan_interval_sec"])
    CFG_RETRY_SEC = int(cfg["cfg_retry_sec"])

    if not config_is_valid(cfg):
        print("Esperando token valido en config_tb.json...")
        time.sleep(CFG_RETRY_SEC)
        continue

    TB_URL = cfg["url"].rstrip("/")
    TB_TOKEN = cfg["token"]

    try:
        files = sorted(f for f in os.listdir(NOTB_DIR) if f.startswith("NO_"))

        for fname in files:
            path = os.path.join(NOTB_DIR, fname)
            print(f"?? Procesando {fname}")

            with open(path, "r") as f:
                lines = f.readlines()

            if len(lines) <= 1:
                continue

            data_lines = lines[1:]
            all_sent = True

            for line in data_lines:
                parsed = parse_line(line)
                if not parsed:
                    continue

                ts, data = parsed

                if not send_to_tb(TB_URL, TB_TOKEN, ts, data):
                    print("? Error enviando a ThingsBoard")
                    all_sent = False
                    break

                print(f"?? Enviado OK {ts}")

            if all_sent:
                os.remove(path)
                print(f"?? Archivo {fname} eliminado")

        time.sleep(SCAN_INTERVAL_SEC)

    except Exception as e:
        print(f"?? Error general: {e}")
        time.sleep(10)
