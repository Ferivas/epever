#!/usr/bin/env bash
#
# Instalador del sistema Epever Modbus -> ThingsBoard.
# Uso:
#   sudo ./install.sh
#   TB_URL=https://mi-servidor TB_TOKEN=mi_token sudo -E ./install.sh
#   sudo ./install.sh --user pi
#
set -euo pipefail

SCRIPT_PATH="$(readlink -f "${BASH_SOURCE[0]}")"
PROJECT_DIR="$(cd -- "$(dirname -- "$SCRIPT_PATH")" && pwd)"

info() { printf '[install] %s\n' "$*"; }
warn() { printf '[install] AVISO: %s\n' "$*" >&2; }
die()  { printf '[install] ERROR: %s\n' "$*" >&2; exit 1; }

usage() {
    cat <<EOF
Uso: sudo ./install.sh [--user USUARIO]

Opciones:
  --user USUARIO   Usuario que ejecutará los servicios systemd.
                   Por defecto se usa el usuario que invocó sudo.

Variables opcionales (solo al crear config_tb.json):
  TB_URL           URL de ThingsBoard (por defecto https://thingsboard.cloud)
  TB_TOKEN         Token de acceso del dispositivo.
                   Sin token real, notb_to_tb.service no arrancará.
EOF
}

for arg in "$@"; do
    if [[ "$arg" == "-h" || "$arg" == "--help" ]]; then
        usage
        exit 0
    fi
done

if [[ "$(id -u)" -ne 0 ]]; then
    info "Se requieren permisos de root; reintentando con sudo..."
    exec sudo -E bash "$SCRIPT_PATH" "$@"
fi

SERVICE_USER="${SUDO_USER:-}"
while [[ $# -gt 0 ]]; do
    case "$1" in
        --user)
            [[ $# -ge 2 ]] || die "--user requiere un nombre de usuario"
            SERVICE_USER="$2"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            die "Opción desconocida: $1"
            ;;
    esac
done

[[ -n "$SERVICE_USER" ]] || die "No se pudo detectar el usuario. Usa --user USUARIO."
id "$SERVICE_USER" >/dev/null 2>&1 || die "El usuario '$SERVICE_USER' no existe."

VENV_DIR="$PROJECT_DIR/venv"
DATOS_DIR="$PROJECT_DIR/DATOS"
NOTB_DIR="$PROJECT_DIR/NOTB"
CFG_FILE="$PROJECT_DIR/config_tb.json"
LEGACY_CFG_FILE="$PROJECT_DIR/tb_config.json"

info "Proyecto:      $PROJECT_DIR"
info "Usuario:       $SERVICE_USER"
info "Entorno:       $VENV_DIR"
info "Configuración: $CFG_FILE"

# -----------------------------
# Dependencias del sistema
# -----------------------------
info "Instalando paquetes del sistema..."
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends python3 python3-venv python3-pip

# -----------------------------
# Entorno virtual y módulos Python
# -----------------------------
if [[ ! -x "$VENV_DIR/bin/python" ]]; then
    info "Creando entorno virtual..."
    python3 -m venv "$VENV_DIR"
else
    info "Reutilizando entorno virtual existente."
fi

PYTHON_VERSION="$("$VENV_DIR/bin/python" -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
if ! "$VENV_DIR/bin/python" -c 'import sys; sys.exit(0 if sys.version_info < (3, 12) else 1)'; then
    warn "Python $PYTHON_VERSION puede no ser compatible con pymodbus 2.5.3."
fi

info "Instalando pymodbus 2.5.3, pyserial y requests..."
"$VENV_DIR/bin/python" -m pip install --disable-pip-version-check \
    "pymodbus==2.5.3" pyserial requests

PYMODBUS_VERSION="$("$VENV_DIR/bin/python" -c 'import pymodbus; print(pymodbus.__version__)')"
[[ "$PYMODBUS_VERSION" == "2.5.3" ]] \
    || die "Se esperaba pymodbus 2.5.3, pero se instaló $PYMODBUS_VERSION"

"$VENV_DIR/bin/python" -c \
    'from pymodbus.client.sync import ModbusSerialClient; import serial, requests' \
    || die "No se pudieron importar pymodbus, pyserial o requests"

# -----------------------------
# Directorios y configuración
# -----------------------------
install -d -m 755 -o "$SERVICE_USER" -g "$SERVICE_USER" "$DATOS_DIR" "$NOTB_DIR"

if [[ ! -f "$CFG_FILE" && -f "$LEGACY_CFG_FILE" ]]; then
    info "Migrando tb_config.json a config_tb.json..."
    mv "$LEGACY_CFG_FILE" "$CFG_FILE"
fi

if [[ ! -f "$CFG_FILE" ]]; then
    info "Creando config_tb.json inicial..."
    TB_URL="${TB_URL:-https://thingsboard.cloud}" \
    TB_TOKEN="${TB_TOKEN:-ACCESS_TOKEN_DEL_DISPOSITIVO}" \
    "$VENV_DIR/bin/python" - "$CFG_FILE" <<'PY'
import json
import os
import sys

cfg = {
    "url": os.environ["TB_URL"],
    "token": os.environ["TB_TOKEN"],
    "scan_interval_sec": 30,
    "cfg_retry_sec": 10,
}
with open(sys.argv[1], "w") as f:
    json.dump(cfg, f, indent=4)
    f.write("\n")
PY
else
    info "Se conserva config_tb.json existente."
fi

chown "$SERVICE_USER:$SERVICE_USER" "$CFG_FILE"
chmod 600 "$CFG_FILE"

# -----------------------------
# UART nativo del Raspberry Pi
# -----------------------------
UART_CHANGED=0
NEEDS_RELOGIN=0

BOOT_CONFIG=""
if [[ -f /boot/firmware/config.txt ]]; then
    BOOT_CONFIG=/boot/firmware/config.txt
elif [[ -f /boot/config.txt ]]; then
    BOOT_CONFIG=/boot/config.txt
fi

if [[ -n "$BOOT_CONFIG" ]]; then
    backup="${BOOT_CONFIG}.bak.$(date +%Y%m%d%H%M%S)"
    cp -a "$BOOT_CONFIG" "$backup"

    if grep -qE '^[[:space:]]*enable_uart=' "$BOOT_CONFIG"; then
        sed -i -E 's|^[[:space:]]*enable_uart=.*|enable_uart=1|' "$BOOT_CONFIG"
    else
        printf '\n# UART para Epever Modbus\nenable_uart=1\n' >> "$BOOT_CONFIG"
    fi

    if cmp -s "$backup" "$BOOT_CONFIG"; then
        rm -f "$backup"
    else
        UART_CHANGED=1
        info "Backup de $BOOT_CONFIG en $backup"
    fi
else
    warn "No se encontró config.txt; habilita manualmente enable_uart=1."
fi

CMDLINE=""
if [[ -f /boot/firmware/cmdline.txt ]]; then
    CMDLINE=/boot/firmware/cmdline.txt
elif [[ -f /boot/cmdline.txt ]]; then
    CMDLINE=/boot/cmdline.txt
fi

if [[ -n "$CMDLINE" ]]; then
    backup="${CMDLINE}.bak.$(date +%Y%m%d%H%M%S)"
    cp -a "$CMDLINE" "$backup"

    sed -i -E \
        's/[[:space:]]*console=(serial0|ttyAMA0|ttyS0)(,[0-9]+)?//g' \
        "$CMDLINE"

    if cmp -s "$backup" "$CMDLINE"; then
        rm -f "$backup"
    else
        UART_CHANGED=1
        info "Backup de $CMDLINE en $backup"
    fi
else
    warn "No se encontró cmdline.txt; deshabilita manualmente la consola serial."
fi

for svc in serial-getty@serial0.service serial-getty@ttyAMA0.service; do
    systemctl disable --now "$svc" >/dev/null 2>&1 || true
done

if id -nG "$SERVICE_USER" | grep -qw dialout; then
    info "El usuario ya pertenece al grupo dialout."
else
    usermod -aG dialout "$SERVICE_USER"
    NEEDS_RELOGIN=1
    info "Usuario añadido al grupo dialout."
fi

if [[ -e /dev/serial0 ]]; then
    info "Puerto serial detectado: /dev/serial0"
else
    warn "/dev/serial0 no existe todavía; puede requerir reiniciar el Raspberry Pi."
fi

chown -R "$SERVICE_USER:$SERVICE_USER" "$VENV_DIR"

# -----------------------------
# Servicios systemd
# -----------------------------
info "Creando servicios systemd..."
cat > /etc/systemd/system/epever-modbus.service <<EOF
[Unit]
Description=Epever Modbus Reader
After=network.target

[Service]
User=$SERVICE_USER
Group=$SERVICE_USER
WorkingDirectory=$PROJECT_DIR
ExecStart="$VENV_DIR/bin/python" "$PROJECT_DIR/epevercsv_qod.py"
Environment=PYTHONUNBUFFERED=1
Restart=always
RestartSec=5
Nice=10

[Install]
WantedBy=multi-user.target
EOF

cat > /etc/systemd/system/notb_to_tb.service <<EOF
[Unit]
Description=Send NOTB data to ThingsBoard
After=network-online.target
Wants=network-online.target

[Service]
User=$SERVICE_USER
Group=$SERVICE_USER
WorkingDirectory=$PROJECT_DIR
ExecCondition="$VENV_DIR/bin/python" "$PROJECT_DIR/notb_to_tb.py" --check-config
ExecStart="$VENV_DIR/bin/python" "$PROJECT_DIR/notb_to_tb.py"
Environment=PYTHONUNBUFFERED=1
Restart=always
RestartSec=10
Nice=10

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable epever-modbus.service notb_to_tb.service

info "Iniciando servicios..."
if systemctl start epever-modbus.service; then
    info "epever-modbus.service: $(systemctl is-active epever-modbus.service || true)"
else
    warn "epever-modbus.service no pudo iniciarse; revisa /dev/serial0 y los logs."
fi

if systemctl start notb_to_tb.service; then
    info "notb_to_tb.service: $(systemctl is-active notb_to_tb.service || true)"
else
    warn "notb_to_tb.service no pudo iniciarse; revisa config_tb.json y los logs."
fi

if "$VENV_DIR/bin/python" "$PROJECT_DIR/notb_to_tb.py" --check-config >/dev/null 2>&1; then
    CONFIG_STATUS="válida"
else
    CONFIG_STATUS="pendiente (token/URL reales)"
fi

echo
info "Instalación completada."
info "Configuración ThingsBoard: $CONFIG_STATUS"
info "Archivo de configuración:  $CFG_FILE"
info "Logs: journalctl -u epever-modbus.service -f"
info "      journalctl -u notb_to_tb.service -f"

if [[ "$UART_CHANGED" -eq 1 || "$NEEDS_RELOGIN" -eq 1 || ! -e /dev/serial0 ]]; then
    echo
    warn "Reinicia el Raspberry Pi para aplicar UART y grupos: sudo reboot"
fi

if [[ "$CONFIG_STATUS" != "válida" ]]; then
    echo
    warn "Edita $CFG_FILE con una URL y un token reales y luego ejecuta:"
    warn "  sudo systemctl start notb_to_tb.service"
fi
