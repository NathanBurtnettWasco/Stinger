# Stinger Architecture Overview (descriptive, not a plan)

## Purpose

This document describes the **runtime architecture** of Stinger: what components exist and what they are responsible for. It avoids implementation plans and speculative future features.

## Core runtime components

### UI Layer (PyQt)

- Presents the **Main / Debug / Admin** tabs.
- Renders per-port status, pressure visualization, and results.
- Exposes the two per-port actions: **Primary action** and **Cancel**.
- Does **not** own hardware timing; it reflects the state of the system.

### Per-port Controller (Port A, Port B)

Each port controller owns:

- the port’s state machine (current state, permitted actions, transitions)
- the active test run (serial number, active parameters, recorded measurements)
- coordination of hardware calls for that port (setpoint changes, solenoid routing, DI monitoring)

### Hardware Abstraction Layer

Per port:

- **Alicat**: setpoint + ramp behavior + readback
- **DAQ** (or equivalent): reads micro-switch state; optionally reads analog pressure inputs
- **Solenoid outputs**: route/vent/enable states needed for the test

### Data Layer (Database)

- Loads **work order context** and **test parameters** (typically from `ProductTestParameters`).
- Writes **test results** per port + serial number.
- Optionally writes diagnostic snapshots (only if required by operations).

## Key constraints that shape the design

- **Two-port independence**: Port A and Port B must not block each other.
- **Operator-driven gating**: some steps intentionally wait for the operator (e.g., “Press Cycle” step).
- **Touch-first UI**: the primary action must be obvious, large, and context-aware.

