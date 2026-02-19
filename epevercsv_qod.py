# -*- coding: utf-8 -*-
"""
Created on Mon Feb  9 16:11:26 2026

@author: Fernando
"""

from pymodbus.client.sync import ModbusSerialClient
import time
import csv
import os
from datetime import datetime

# -----------------------------
# CONFIGURACIÓN
# -----------------------------
PORT = "/dev/serial0"
BAUDRATE = 115200
SLAVE_ID = 1

READ_INTERVAL_SEC = 5
LOG_INTERVAL_MIN = 5   # N minutos (00,05,10...)

# -----------------------------
# DIRECTORIO BASE DEL SCRIPT
# -----------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DATOS_DIR = os.path.join(BASE_DIR, "DATOS")
NOTB_DIR  = os.path.join(BASE_DIR, "NOTB")

os.makedirs(DATOS_DIR, exist_ok=True)
os.makedirs(NOTB_DIR, exist_ok=True)

# -----------------------------
# MAC eth0 (sin :)
# -----------------------------
def get_mac_eth0():
    try:
        with open("/sys/class/net/eth0/address") as f:
            return f.read().strip().replace(":", "").upper()
    except:
        return "UNKNOWNMAC"

DEVICE_MAC = get_mac_eth0()

# -----------------------------
# MODBUS
# -----------------------------
client = ModbusSerialClient(
    method="rtu",
    port=PORT,
    baudrate=BAUDRATE,
    parity='N',
    stopbits=1,
    bytesize=8,
    timeout=1
)

if not client.connect():
    print("❌ No se pudo conectar al controlador")
    exit(1)

print("✅ Conectado al controlador solar")
print(f"🆔 MAC RPi: {DEVICE_MAC}")

# -----------------------------
# FUNCIONES
# -----------------------------
def read_block(addr, count):
    rr = client.read_input_registers(addr, count, unit=SLAVE_ID)
    if rr.isError():
        return None
    return rr.registers

def u32(low, high):
    return (high << 16) | low

def get_datos_filename(dt):
    return os.path.join(
        DATOS_DIR,
        f"{dt.strftime('%y%m')}_{DEVICE_MAC}.csv"
    )

def get_notb_filename(dt):
    return os.path.join(
        NOTB_DIR,
        f"NO_{dt.strftime('%y%m')}_{DEVICE_MAC}.txt"
    )

def write_header_if_needed(filename):
    if not os.path.exists(filename):
        with open(filename, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "IDtrama", "Fecha", "Hora", "IDMAC",
                "pv_v", "pv_i", "pv_pwr",
                "bat_v", "bat_i", "bat_pwr",
                "load_v", "load_i", "load_pwr",
                "qod"
            ])

def write_csv(filename, row):
    with open(filename, "a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(row)

# -----------------------------
# ACUMULADORES
# -----------------------------
acc = {
    "pv_v": 0.0, "pv_i": 0.0, "pv_p": 0.0,
    "bat_v": 0.0, "bat_i": 0.0, "bat_p": 0.0,
    "load_v": 0.0, "load_i": 0.0, "load_p": 0.0
}

ok_count = 0
total_count = 0
current_slot = None

# -----------------------------
# LOOP PRINCIPAL
# -----------------------------
try:
    while True:
        now = datetime.now()
        slot_id = (now.day, now.hour, now.minute // LOG_INTERVAL_MIN)

        total_count += 1

        regs = read_block(0x3100, 16)
        if regs:
            # ☀️ Panel
            pv_v = regs[0] / 100.0
            pv_i = regs[1] / 100.0
            pv_p = u32(regs[2], regs[3]) / 100.0

            # 🔋 Batería
            bat_v = regs[4] / 100.0
            bat_i = regs[5] / 100.0
            bat_p = u32(regs[6], regs[7]) / 100.0

            # 💡 Carga
            load_v = regs[12] / 100.0
            load_i = regs[13] / 100.0
            load_p = u32(regs[14], regs[15]) / 100.0

            if current_slot is None:
                current_slot = slot_id

            if slot_id == current_slot:
                acc["pv_v"] += pv_v
                acc["pv_i"] += pv_i
                acc["pv_p"] += pv_p

                acc["bat_v"] += bat_v
                acc["bat_i"] += bat_i
                acc["bat_p"] += bat_p

                acc["load_v"] += load_v
                acc["load_i"] += load_i
                acc["load_p"] += load_p

                ok_count += 1
        else:
            print("⚠️ Error leyendo Modbus")

        # Cambio de ventana → guardar promedio
        if slot_id != current_slot and ok_count > 0:
            avg = {k: acc[k] / ok_count for k in acc}
            qod = round((ok_count * 100.0) / total_count, 1)

            datos_file = get_datos_filename(now)
            notb_file  = get_notb_filename(now)

            write_header_if_needed(datos_file)
            write_header_if_needed(notb_file)

            row = [
                "A",
                now.strftime("%d/%m/%y"),
                now.strftime("%H:%M:%S"),
                DEVICE_MAC,
                round(avg["pv_v"], 2),
                round(avg["pv_i"], 2),
                round(avg["pv_p"], 2),
                round(avg["bat_v"], 2),
                round(avg["bat_i"], 2),
                round(avg["bat_p"], 2),
                round(avg["load_v"], 2),
                round(avg["load_i"], 2),
                round(avg["load_p"], 2),
                qod
            ]

            write_csv(datos_file, row)
            write_csv(notb_file, row)

            print(f"💾 Promedio guardado ({ok_count}/{total_count}) QOD={qod}%")

            # Reset ventana
            for k in acc:
                acc[k] = 0.0

            ok_count = 0
            total_count = 0
            current_slot = slot_id

        time.sleep(READ_INTERVAL_SEC)

except KeyboardInterrupt:
    print("\n⏹ Finalizando")

finally:
    client.close()
