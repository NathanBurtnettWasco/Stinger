# Stinger Hardware Description (factual)

This document describes the hardware Stinger interacts with. It intentionally avoids speculative YAML schemas and unconfirmed units.

## System topology

Stinger is a **dual-port** system:

- **Port A** hardware is independent from **Port B** hardware.
- Both ports are controlled from one application instance.

## Operating environment

- **Location**: cleanroom
- **Gas**: high purity N₂
- **Pressure capability**: system operates from vacuum regions up through ~110 PSI (product-dependent)

## Per-port hardware (required)

Each port has:

- **Alicat pressure controller**
  - Used to command pressure setpoints and ramp behavior.
  - **Not rated for torr-level precision** but used for control.
  - Pressure port: Always pressurized high.
  - Exhaust port: Connected to solenoid (switches between atmosphere and vacuum).
  - Complex interaction: When controlling pressure in vacuum and wants to come up, switches to atmosphere for relay to exhaust back up.
- **Solenoid output**
  - Controls exhaust path (switches between atmosphere and vacuum).
  - Connected to Alicat exhaust port.
- **Digital inputs** (via DB9 connector)
  - Up to 9 digital inputs per port.
  - Reads micro-switch state (NO/NC terminals).
  - NO/NC: Switch states (can be HIGH or LOW depending on switch configuration).
  - **No watchdog**: Watchdog is only in Functional Stand, not Stinger.
- **Pressure measurement** (dual-source)
  - **Alicat**: Used for control (readback available but not used for precision measurement).
  - **Transducer**: Used for measurement/recording (authoritative for pass/fail).
    - Rated for +/- 1.4 torr accuracy.
    - 0.5-4.5V ratiometric transducer.
  - Connected via LabJack T7-Pro.
    - Noise levels have been challenging (may be DAQ-related).

## Shared / system-level hardware (optional)

Depending on the stand:

- shared pressure source or shared safety interlocks
- shared venting hardware
- E-stop and safety circuits

## Signal inventory (to fill in)

For each port, record:

- **Alicat connection**: COM / address / protocol
- **Solenoid outputs**: device + channel names and what each state means physically
- **Digital inputs**: device + line names and what HIGH/LOW means
- **Pressure measurement**: source, scaling, units, filtering expectations

These details are tracked as questions in `docs/90_OPEN_QUESTIONS.md` until confirmed.

