# LabJack T7‑Pro Reference (High‑Speed Focus)

This document consolidates the LabJack T7‑Pro technical reference for integration planning.
It intentionally omits WiFi details to focus on high‑speed USB/Ethernet operation.

## Overview

The LabJack T7‑Pro is a multifunction DAQ with USB and Ethernet connectivity. It adds a
24‑bit low‑speed sigma‑delta ADC, a battery‑backed RTC, and microSD storage for
standalone logging. The device is controlled via Modbus TCP; the recommended API is the
LabJack LJM library.

Key features:
- 14 analog inputs (single‑ended) or 7 differential pairs.
- 2 analog outputs (DAC0/DAC1).
- 23 digital I/O lines with extended features (counters, PWM, etc.).
- 10 µA and 200 µA fixed current sources.
- Command‑response (low latency) and stream mode (high throughput).

## Hardware Interfaces

- USB Type‑B (power is always supplied via USB).
- Ethernet 10/100Base‑T.
- Screw terminals: subset of AIN/DAC/DIO/current source.
- DB15 + DB37: full I/O breakout; DB37 includes additional AIN/DIO.

## Analog Inputs (AIN)

- Channels: `AIN0`–`AIN13`.
- Single‑ended (14) or differential (7).
- Input ranges: ±10 V, ±1 V, ±0.1 V, ±0.01 V.
- Standard T7 uses high‑speed 16‑bit ADC; T7‑Pro adds 24‑bit low‑speed ADC.
- Resolution index controls speed vs noise; higher index is slower but lower noise.
- Command‑response AIN reads return volts; stream returns binary values (LJM converts to volts).
- Stream mode on T7‑Pro does **not** support high‑resolution indices 9–12.

### AIN Extended Features (AIN‑EF)

AIN‑EF provides common analog processing (average/min/max, RMS, resistance, RTD,
thermocouple, etc.). AIN‑EF is command‑response only and is not available in stream mode.

### Floating Inputs

Floating channels read non‑zero voltages due to high input impedance. Tie unused AIN
channels to GND if the readings are used for logic or diagnostics.

## Analog Outputs (DAC)

- Channels: `DAC0`, `DAC1`.
- T7 DAC range: ~0–5 V, 12‑bit resolution (~1.2 mV steps).
- Source impedance: ~50 Ω; max output current ~20 mA.
- Output droop occurs under load (voltage divider with 50 Ω source impedance).
- Power‑up default: enabled at minimum voltage unless configured otherwise.

## Digital I/O (DIO)

- Channels: `DIO0`–`DIO22` (aliases: `FIO`, `EIO`, `CIO`, `MIO`).
- 3.3 V logic, tri‑state (input, output‑high, output‑low).
- Pull‑ups: ~100 kΩ to 3.3 V (not switchable on T7).
- Extended features: counters, timers, PWM, quadrature input, frequency/period, pulse width.
- Protocols: I2C, SPI, SBUS, 1‑Wire, UART (asynchronous serial) via DIO lines.

### T7 connector DIO breakout (pinout references)

The T7 routes its digital I/O across two connectors:

- **DB37**: FIO0–FIO7 and MIO0–MIO2  
  (see LabJack datasheet: https://support.labjack.com/docs/16-0-db37-t7-only-t-series-datasheet)
- **DB15**: EIO0–EIO7 and CIO0–CIO3  
  (see LabJack datasheet: https://support.labjack.com/docs/17-0-db15-t-series-datasheet)

For Stinger’s DIO numbering:
- `DIO0–DIO7` = `FIO0–FIO7` (DB37)
- `DIO8–DIO15` = `EIO0–EIO7` (DB15)
- `DIO16–DIO19` = `CIO0–CIO3` (DB15)
- `DIO20–DIO22` = `MIO0–MIO2` (DB37)

### DIO Bitmask Control

Use DIO bitmask registers to set directions and states for multiple DIO lines at once.
Read `DIO_STATE` (not `DIO#`) to read without changing direction.

## Fixed Current Outputs

- 10 µA and 200 µA sources for resistive sensors (RTD/thermistor) or bridge excitation.

## Communication Model

- Device is a Modbus TCP server.
- Command‑response: low latency, best for control/feedback.
- Stream mode: buffered, high throughput, higher latency.

### Stream Mode (High‑Speed)

- T7 max sample rate: 100 ksamples/s (single channel, low resolution, ±10 V).
- Scan rate depends on channel count: `SampleRate = ScanRate × NumChannels`.
- Ethernet provides the best throughput; USB is typically slower.
- If any AIN is in the scan list, AIN command‑response reads are blocked during stream.
- Stream data is interleaved by scan: `[ch1_s1, ch2_s1, ..., chN_s1, ch1_s2, ...]`.
- 16‑bit stream data is default; 32‑bit stream data uses `STREAM_DATA_CAPTURE_16`.

## LJM Library (Recommended API)

- Cross‑platform driver for T‑series devices.
- Name‑based read/write (`AIN0`, `DAC0`, `DIO0`, etc.).
- Handles calibration conversion for AIN voltages in stream/command‑response.
- Provides streaming, device discovery, reconnection, and utility functions.

## Lua Scripting (On‑Device)

- Runs Lua scripts directly on the device for autonomous behavior.
- Scripts can be saved to flash and enabled at power‑up.
- Useful for local control loops, preprocessing, and buffered logging.
- Limited RAM; scripts must be compact.
- Lua uses single‑precision floats on T7 (24‑bit integer precision limit).

## RTC + microSD

- Battery‑backed RTC for timestamped measurements.
- microSD for standalone data logging using Lua + file‑IO registers.

## Practical Integration Notes

- Avoid reading AIN via command‑response while streaming analog inputs.
- Use Ethernet for highest sustained throughput and lowest packet latency.
- If 5 V logic is required, use a level shifter or buffer IC.
- For precise analog output under load, buffer the DAC or use external reference circuitry.

## Stinger Discovery + Bring-up

### Required drivers (Windows)

The Python package `labjack-ljm` requires the native LJM driver (`LabJackM.dll`).
Install the LabJack LJM driver from LabJack before running discovery scripts or the UI.

### Discovery script (repo)

Use the repo helper to find connected devices and read one port configuration:

```
python scripts/labjack_discovery.py
python scripts/labjack_discovery.py --port port_b
python scripts/labjack_discovery.py --connection USB --identifier ANY
```

The script reports:
- LJM discovery results (device type, connection, serial, IP)
- Handle info (device, connection, serial, IP, port)
- One-shot AIN + DIO reads using the current `stinger_config.yaml` mapping

### Latest local discovery results (2026-01-22)

- LJM discovery returned **1 device**
- `device_type=7`, `connection=1` (USB), `serial=470038756`
- IP reported as `0.0.0.0` (Ethernet not yet assigned / not reported by LJM)
- Handle opened successfully; basic AIN/DIO reads succeeded
- DIO scan (`DIO0–DIO19`) read **1.0** for all lines (inputs floating high)

Action: If Ethernet is required, configure the T7 IP (DHCP/static) and re-run discovery
to capture the assigned IP address.
