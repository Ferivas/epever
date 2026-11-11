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

El instalador usa la ruta real del proyecto. La estructura típica es:
```text

/home/pi/epever/
│
├── install.sh
├── epevercsv_qod.py
├── notb_to_tb.py
├── config_tb.json
├── DATOS/
└── NOTB/
```

## ⚙️ Requisitos del Sistema

- Raspberry Pi (recomendado RPi 3B+ o superior)
- Raspberry Pi OS con acceso a Internet
- Python 3.9–3.11 (recomendado; `pymodbus==2.5.3` no está probado en 3.12+)
- `git` instalado
- Puerto UART interno habilitado
- Controlador Epever compatible con Modbus RTU

---

## 🚀 Instalación desde GitHub en Raspberry Pi (recomendada)

Estos pasos se ejecutan directamente en el Raspberry Pi, con el controlador
Epever conectado por RS485 al UART.

### 1️⃣ Instalar Git

```bash
sudo apt update
sudo apt install -y git
```

### 2️⃣ Clonar el repositorio

```bash
cd ~
git clone https://github.com/Ferivas/epever.git
cd epever
```

La instalación se hará en la ruta donde se clone el repositorio. En este
ejemplo será `/home/pi/epever`.

### 3️⃣ Ejecutar el instalador

```bash
chmod +x install.sh
sudo ./install.sh
```

El instalador se encarga de:

- Instalar `python3-venv`, `pyserial`, `requests` y `pymodbus==2.5.3`.
- Crear el entorno virtual `venv/`.
- Habilitar el UART nativo y deshabilitar la consola serial.
- Añadir el usuario al grupo `dialout`.
- Crear `DATOS/`, `NOTB/` y `config_tb.json` si no existen.
- Crear, habilitar e iniciar los servicios systemd.
- Configurar los servicios con la ruta real del proyecto y el usuario que
  invocó `sudo`.

### 4️⃣ Configurar el token de ThingsBoard

Se puede pasar durante la instalación:

```bash
TB_URL=https://thingsboard.cloud TB_TOKEN=tu_token_real sudo -E ./install.sh
```

O editar el archivo después de instalar:

```bash
nano ~/epever/config_tb.json
```

```json
{
  "url": "https://thingsboard.cloud",
  "token": "tu_token_real",
  "scan_interval_sec": 30,
  "cfg_retry_sec": 10
}
```

Sin un token real, `notb_to_tb.service` queda instalado y habilitado, pero no
arranca hasta que se configure. El instalador valida la configuración con:

```bash
~/epever/venv/bin/python ~/epever/notb_to_tb.py --check-config
```

Si devuelve error, corrige `config_tb.json` y arranca el servicio:

```bash
sudo systemctl start notb_to_tb.service
```

### 5️⃣ Reiniciar si el instalador modificó el UART

Si el instalador añadió `enable_uart=1`, eliminó la consola serial o añadió el
usuario a `dialout`, hay que reiniciar:

```bash
sudo reboot
```

### 6️⃣ Verificar la instalación

```bash
systemctl status epever-modbus.service
systemctl status notb_to_tb.service
```

Logs en tiempo real:

```bash
journalctl -u epever-modbus.service -f
journalctl -u notb_to_tb.service -f
```

### Actualizar una instalación existente

```bash
cd ~/epever
git pull
sudo ./install.sh
```

`install.sh` es idempotente y conserva `config_tb.json`, `DATOS/` y `NOTB/`.
Volverá a generar las unidades systemd y actualizará las dependencias del
entorno virtual.

### Solución de problemas rápida

- `/dev/serial0` no existe: revisar `enable_uart=1`, la consola serial y
  reiniciar el Raspberry Pi.
- Error de permisos en el puerto serial: confirmar que el usuario está en el
  grupo `dialout` y reiniciar o cerrar sesión.
- `notb_to_tb.service` inactivo: ejecutar `--check-config` y revisar
  `config_tb.json`.
- Ver los últimos errores de un servicio:

```bash
journalctl -u epever-modbus.service -n 50 --no-pager
journalctl -u notb_to_tb.service -n 50 --no-pager
```

---

## 🔧 Instalación Manual Paso a Paso (alternativa)

Usar esta sección solo si no se quiere ejecutar `install.sh`. El instalador
automático ya realiza todos estos pasos.

### 1️⃣ Crear carpeta del proyecto

```bash
mkdir -p /home/pi/epever
cd /home/pi/epever
mkdir DATOS NOTB
```

Copiar dentro:
- `install.sh`
- `epevercsv_qod.py`
- `notb_to_tb.py`

---

### 2️⃣ Crear entorno virtual (virtualenv)

```bash
sudo apt update
sudo apt install python3-venv -y

cd /home/pi/epever
python3 -m venv venv
source venv/bin/activate
```

---

### 3️⃣ Instalar dependencias

Se usa una versión fija de pymodbus para estabilidad.

```bash
pip install pymodbus==2.5.3 pyserial requests
```

Verificar:

```bash
python -c "import pymodbus; print(pymodbus.__version__)"
```

Debe mostrar:

```text
2.5.3
```

---

### 4️⃣ Configuración del UART del Raspberry

Editar `/boot/firmware/config.txt` (Raspberry Pi OS Bookworm) o
`/boot/config.txt` (versiones anteriores).

Añadir:

```text
enable_uart=1
```

Deshabilitar consola serial:

```bash
sudo raspi-config
```

Seleccionar `Interface Options → Serial Port` y responder:

- Login shell: `NO`
- Serial port hardware: `YES`

Reiniciar:

```bash
sudo reboot
```

---

## 📊 Script 1: Lectura Modbus

epevercsv_qod.py realiza:

- Lecturas Modbus cada 5 segundos
- Promedios cada N minutos
- Cálculo de QoD (Quality of Data)
- Guarda archivo mensual en DATOS
- Genera archivo espejo en NOTB

Formato CSV:
IDtrama,Fecha,Hora,IDMAC,pv_v,pv_i,pv_pwr,bat_v,bat_i,bat_pwr,load_v,load_i,load_pwr,qod

---

## ☁ Script 2: Envío a ThingsBoard

notb_to_tb.py:

1. Escanea carpeta NOTB
2. Envía cada línea a ThingsBoard
3. Si el envío es exitoso → borra el archivo

---

## 🔐 Archivo de Configuración JSON

Ubicación:
```text
<ruta-del-proyecto>/config_tb.json
```

Por ejemplo, si se clonó en `/home/pi/epever`:

```text
/home/pi/epever/config_tb.json
```

Contenido inicial:

```json
{
  "url": "https://thingsboard.cloud",
  "token": "ACCESS_TOKEN_DEL_DISPOSITIVO",
  "scan_interval_sec": 30,
  "cfg_retry_sec": 10
}
```

El archivo se crea automáticamente si no existe y tiene permisos `600`. Las
claves deben estar en minúscula. El script espera hasta que el token sea válido
antes de enviar datos.

Si existe el nombre antiguo `tb_config.json`, se migra automáticamente a
`config_tb.json` al arrancar.

El servicio systemd valida la configuración antes de arrancar mediante:

```bash
venv/bin/python notb_to_tb.py --check-config
```

Si el token sigue siendo el placeholder o la URL no es válida, el comando
devuelve error y systemd omite el arranque de `notb_to_tb.service`.

---

## 🧰 Servicios systemd

`install.sh` genera estas unidades usando la ruta real del proyecto y el
usuario que invocó `sudo`. Los ejemplos siguientes usan `/home/pi/epever`.

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
Group=pi
WorkingDirectory=/home/pi/epever
ExecStart=/home/pi/epever/venv/bin/python /home/pi/epever/epevercsv_qod.py
Environment=PYTHONUNBUFFERED=1
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
After=network-online.target
Wants=network-online.target

[Service]
User=pi
Group=pi
WorkingDirectory=/home/pi/epever
ExecCondition=/home/pi/epever/venv/bin/python /home/pi/epever/notb_to_tb.py --check-config
ExecStart=/home/pi/epever/venv/bin/python /home/pi/epever/notb_to_tb.py
Environment=PYTHONUNBUFFERED=1
Restart=always
RestartSec=10
Nice=10

[Install]
WantedBy=multi-user.target
```
---

### Activar servicios

`install.sh` ya ejecuta estos comandos. Para hacerlo manualmente:

```bash
sudo systemctl daemon-reload
sudo systemctl enable epever-modbus.service
sudo systemctl enable notb_to_tb.service
sudo systemctl start epever-modbus.service
sudo systemctl start notb_to_tb.service
```

Ver estado:

```bash
systemctl status epever-modbus.service
systemctl status notb_to_tb.service
```

Si `notb_to_tb.service` está inactivo, revisar la configuración:

```bash
~/epever/venv/bin/python ~/epever/notb_to_tb.py --check-config
```

Logs en tiempo real:

```bash
journalctl -u epever-modbus.service -f
journalctl -u notb_to_tb.service -f
```

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
tb_config.json

---

## 🚀 Resultado Final

El sistema permitirá:

- Lectura robusta del bus Modbus Epever
- Cálculo de promedios y QoD
- Almacenamiento mensual de datos
- Envío automático a ThingsBoard
- Operación continua tras reinicio del Raspberry Pi
