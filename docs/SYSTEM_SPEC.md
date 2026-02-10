# Stinger System Spec (authoritative)

This documentation describes **what Stinger is** and **how it behaves** (operator workflow, UI behavior, hardware, data). It intentionally avoids project plans/roadmaps.

## What Stinger is

Stinger is a **dual-port pressure/vacuum switch test stand** for the **Scorpion** product line, operated in a **cleanroom** using **high purity N₂**.

- **Two independent ports** (Port A and Port B)
  - Each port has its own **Alicat** (control), **exhaust solenoid**, **pressure transducer** (authoritative measurement), and **digital inputs** (switch state).
  - Ports run **asynchronously**: one port starting/stopping does not implicitly start/stop the other (except for explicit safety behavior).

## What Stinger does (production context)

Stinger supports multiple production operations (work instructions):

- **QAL 15**: Calibration (includes manual SEI adjustment step)
- **QAL 16**: Calibration Check
- **QAL 17**: Final Test

The selected workflow is driven by **Shop Order context** and the **database parameters** for the active Part/Sequence.

## Pass/fail fundamentals

- **Measured values**: activation pressure and deactivation pressure (captured during the precision test sweep)
- **Acceptance**: **PASS requires BOTH activation AND deactivation to be in-range** for their respective acceptance windows (“bands”)

See `DATABASE_CONTRACT.md` for the exact parameter names and evaluation rules.

## UI mental model

Stinger has three primary UI areas:

- **Main**: operator-facing production workflow (touch-first)
- **Debug**: manual per-port control (ignores/overrides normal PTP/work-order flow)
- **Admin**: read-only observability (hardware, database, state, history)

Debug and Admin are **PIN-gated** to avoid accidental use in production.

See `UI_SPEC.md` and `WORKFLOWS.md`.

## Architecture at a glance (runtime responsibilities)

- **UI (PyQt)**: renders state, accepts operator input; does not own timing-critical hardware loops
- **Per-port controller**: owns the port state machine + test execution for that port
- **Hardware layer**: Alicat control, DAQ/transducer acquisition, digital input sampling, solenoid output control
- **Database layer**: reads work-order context + PTP, writes results (including retests as overwrite)

See `HARDWARE_SPEC.md` and `DATABASE_CONTRACT.md`.

