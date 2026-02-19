# epever
Programa para leer los datos de un cargador solar EPEVER modelo Tracer1210AN vía Modbus
# 📡 Epever Modbus → ThingsBoard (Raspberry Pi)

Sistema para lectura de datos de un controlador solar Epever vía Modbus RTU en Raspberry Pi y envío a ThingsBoard utilizando archivos intermedios.

## 🧩 Arquitectura del Sistema

```text
Controlador Solar EPEVER (Modbus RS485)
                │
                ▼
        Raspberry Pi (UART interno)
                │
    ┌───────────────────────────────┐
    │ Script 1: epevercsv_qod.py    │
    │ - Lectura Modbus              │
    │ - Promedios + QoD             │
    │ - Guarda CSV mensual          │
    │ - Genera archivo NOTB         │
    └───────────────┬───────────────┘
                    │
        ┌───────────▼───────────┐
        │ Carpeta DATOS         │
        │ YYMM_IDMAC.csv        │
        └───────────┬───────────┘
                    │
        ┌───────────▼───────────┐
        │ Carpeta NOTB          │
        │ NO_YYMM_IDMAC.txt     │
        └───────────┬───────────┘
                    │
    ┌───────────────▼──────────────┐
    │ Script 2: notb_to_tb.py      │
    │ - Lee archivos NOTB          │
    │ - Envía a ThingsBoard        │
    │ - Borra archivo enviado      │
    └───────────────┬──────────────┘
                    │
                    ▼
              ThingsBoard Cloud
```


## 📁 Estructura de Directorios

El sistema debe instalarse en:
```text

/home/pi/epever/
│
├── epevercsv_qod.py
├── notb_to_tb.py
├── config_tb.json
├── DATOS/
└── NOTB/
```

## ⚙️ Requisitos del Sistema

- Raspberry Pi (recomendado RPi 3B+ o superior)
- Raspberry Pi OS
- Python 3.9+
- Puerto UART interno habilitado
- Controlador Epever compatible con Modbus RTU

---

## 🔧 Instalación Paso a Paso

### 1️⃣ Crear carpeta del proyecto

mkdir -p /home/pi/epever
cd /home/pi/epever
mkdir DATOS NOTB

Copiar dentro:
- epevercsv_qod.py
- notb_to_tb.py

---

### 2️⃣ Crear entorno virtual (virtualenv)

sudo apt update
sudo apt install python3-venv -y

cd /home/pi/epever
python3 -m venv venv
source venv/bin/activate

---

### 3️⃣ Instalar dependencias

Se usa una versión fija de pymodbus para estabilidad.

pip install pymodbus==2.5.3 pyserial requests

Verificar:
python -c "import pymodbus; print(pymodbus.__version__)"

Debe mostrar:
2.5.3

---

### 4️⃣ Configuración del UART del Raspberry

Editar:
/boot/config.txt

Añadir:
enable_uart=1

Deshabilitar consola serial:
sudo raspi-config
Interface Options → Serial Port
Login shell: NO
Serial port hardware: YES

Reiniciar:
sudo reboot

---

## 📊 Script 1: Lectura Modbus

epevercsv_qod.py realiza:

- Lecturas Modbus cada 5 segundos
- Promedios cada N minutos
- Cálculo de QoD (Quality of Data)
- Guarda archivo mensual en DATOS
- Genera archivo espejo en NOTB

Formato CSV:
IDtrama,Fecha,Hora,IDMAC,pv_v,pv_i,pv_per,bat_v,bat_i,bat_pwr,load_v,load_i,load_pwr

---

## ☁ Script 2: Envío a ThingsBoard

notb_to_tb.py:

1. Escanea carpeta NOTB
2. Envía cada línea a ThingsBoard
3. Si el envío es exitoso → borra el archivo

---

## 🔐 Archivo de Configuración JSON

Ubicación:
/home/pi/epever/config_tb.json

Contenido inicial:
{
  "url": "https://thingsboard.cloud",
  "token": "ACCESS_TOKEN_DEL_DISPOSITIVO",
  "SCAN_INTERVAL_SEC": 30,
  "CFG_RETRY_SEC": 10
}

El script espera hasta que el token sea válido antes de enviar datos.

---

## 🧰 Servicios systemd

### Servicio 1: Lectura Modbus

Archivo:
/etc/systemd/system/epever-modbus.service

Contenido:
```text
[Unit]
Description=Epever Modbus Reader
After=network.target

[Service]
User=pi
WorkingDirectory=/home/pi/epever
ExecStart=/home/pi/epever/venv/bin/python /home/pi/epever/epevercsv_qod.py
Restart=always
RestartSec=5
Nice=10

[Install]
WantedBy=multi-user.target
```
---

### Servicio 2: Envío a ThingsBoard

Archivo:
/etc/systemd/system/notb_to_tb.service

Contenido:
```text
[Unit]
Description=Send NOTB data to ThingsBoard
After=network.target

[Service]
User=pi
WorkingDirectory=/home/pi/epever
ExecStart=/home/pi/epever/venv/bin/python /home/pi/epever/notb_to_tb.py
Restart=always
RestartSec=10
Nice=10

[Install]
WantedBy=multi-user.target
```
---

### Activar servicios

sudo systemctl daemon-reload
sudo systemctl enable epever-modbus.service
sudo systemctl enable notb_to_tb.service
sudo systemctl start epever-modbus.service
sudo systemctl start notb_to_tb.service

Ver estado:
systemctl status epever-modbus.service
systemctl status notb_to_tb.service

Logs en tiempo real:
journalctl -u epever-modbus.service -f
journalctl -u notb_to_tb.service -f

---

## 📈 Verificación de Funcionamiento

1. Revisar carpeta DATOS:
   YYMM_IDMAC.csv

2. Revisar carpeta NOTB:
   NO_YYMM_IDMAC.txt

3. Confirmar recepción en ThingsBoard.

---

## 🛡 Recomendaciones de Robustez

- Usar fuente de alimentación estable para el Raspberry Pi
- Cable RS485 corto y blindado
- Habilitar watchdog si se requiere operación 24/7
- Supervisar CPU:
  systemd-cgtop

---

## 📦 Archivos a Ignorar en GitHub

Agregar al .gitignore:

### Virtualenv
venv/
.env/

### Python
__pycache__/
*.pyc

### Datos locales
DATOS/
NOTB/

### Configuración sensible
config_tb.json

---

## 🚀 Resultado Final

El sistema permitirá:

- Lectura robusta del bus Modbus Epever
- Cálculo de promedios y QoD
- Almacenamiento mensual de datos
- Envío automático a ThingsBoard
- Operación continua tras reinicio del Raspberry Pi
