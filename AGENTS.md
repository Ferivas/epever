# AGENTS.md

Two standalone Python scripts plus a systemd installer for a Raspberry Pi solar controller (EPEVER Tracer1210AN) that reads Modbus RTU and forwards telemetry to ThingsBoard. No package, build system, test suite, or lockfile.

## Layout / data flow

- `epevercsv_qod.py` — reads Modbus every 5s, averages over 5-minute windows, writes monthly CSV rows to `DATOS/` and an identical copy to `NOTB/`. Runs forever.
- `notb_to_tb.py` — polls `NOTB/` every 30s, POSTs each data row to the ThingsBoard telemetry API, deletes a file only after all its rows send successfully. Runs forever unless invoked with `--check-config`.
- `install.sh` — root installer: apt packages, `venv/`, UART setup, `config_tb.json`, and both systemd units.
- Both Python scripts resolve paths from `__file__` (`BASE_DIR`), so `DATOS/` and `NOTB/` are created next to the scripts.

## Config and startup guard

- Canonical config is **`config_tb.json`**; keys are lowercase: `url`, `token`, `scan_interval_sec`, `cfg_retry_sec`. Missing/incomplete config is auto-created with defaults.
- Legacy `tb_config.json` is migrated to `config_tb.json` automatically; do not add new references to the old name.
- `notb_to_tb.py --check-config` exits `0` only for an `http(s)` URL, a non-placeholder token, and positive intervals; it exits `1` otherwise.
- `notb_to_tb.service` uses that command as systemd `ExecCondition`, so the service is skipped until real config values exist. After editing the config, start it manually or reboot.
- `install.sh` installs into the directory containing it and runs services as `$SUDO_USER` (override with `--user`). It enables and starts both units.

## Environment quirks

- Requires `pymodbus==2.5.3`. The code imports `pymodbus.client.sync.ModbusSerialClient` and calls `read_input_registers(..., unit=...)` — both are removed/changed in pymodbus 3.x, so do not "upgrade" the pin.
- `epevercsv_qod.py` hardcodes `/dev/serial0` at 115200 baud, slave ID 1, and reads input registers starting at `0x3100` (16 registers). No env/CLI override.
- Device ID is the `eth0` MAC without colons; falls back to `UNKNOWNMAC` when unavailable.
- UART changes (`enable_uart=1`, removing `console=serial0`) need a reboot. The service user must be in `dialout`.
- Target deployment is a Raspberry Pi, not necessarily `/home/pi/epever`; the installer uses the actual project path.

## Working on this repo

- Verify syntax with:
  ```bash
  bash -n install.sh
  python -m py_compile epevercsv_qod.py notb_to_tb.py
  ```
- There is no test suite. Test `--check-config` in a temp copy with a placeholder config (expect exit `1`) and a real-looking URL/token (expect exit `0`); use a dummy `requests` module if dependencies are not installed.
- Neither script can run to completion on a dev machine: script 1 blocks on the serial port, script 2 loops forever. Exercise pure functions (`parse_line`, `send_to_tb`, `load_or_create_config`, `config_is_valid`) directly.
- `parse_line` requires all 14 CSV columns and silently skips shorter lines. Fields are `pv_pwr`, `bat_pwr`, `load_pwr`, and `qod`.
- The monthly output for a given month is one CSV and one `NO_*.txt` per device MAC; both scripts match files by the `NO_` prefix.
