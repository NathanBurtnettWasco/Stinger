# Stinger Test Sequences (Scorpion)

This document describes operator-visible behavior for the Scorpion test stand. It reflects the current work instructions (QAL 15/16/17) and the parameters loaded from PTP.

## Preconditions

- Work order context is loaded (operator/shop order/part/sequence/qty).
- The port has a valid serial number loaded.
- Hardware for that port is online (Alicat + IO).

## Sequence selection (by operation / sequence)

The stand runs different workflows depending on the operation being performed:

- **QAL 15 — Scorpion Calibration** (install SEI + calibration)
- **QAL 16 — Scorpion Calibration Check**
- **QAL 17 — Scorpion Final Test**

In all cases, the operator uses **Verify Parameters** first to confirm the database parameters exist for the given Work Order / Part ID / Sequence.

### Example: `SPS01414-03` sequences seen in PTP

For `SPS01414-03`, PTP sequences currently present include `300`, `600`, and `650` (plus a smaller `625` family). In saved results (`OrderCalibrationDetail`) those sequences often appear zero-padded as `0300`, `0600`, `0650`.

## QAL 15 — Scorpion Calibration (summary)

High-level steps (single port):

- **Load part** into test port and connect test leads.
- **Locate actuation point at vented pressure** (port pressure 0.00) by rotating the SEI until the switch actuates (UI indicator changes state).
- **Mark electrical/body** (1st mark) and rotate to a safe position.
- **Pressurize port** (UI has a `Pressurize Port` action) until port pressure exceeds the **Target Activation** value.
- **Find pressurized actuation point** and mark the body (2nd mark).
- **Failure check**: 2nd mark position relative to 1st mark determines reset behavior; if “bad”, swap SEI/SBA and restart.
- **Center travel** between marks (3rd mark).
- **Cycle DUT** (performed before precision testing when adjustments are made).
- **Precision test** via `Precision Test` (with `Cancel Precision Test` available while running).
- **Adjust calibration** (spring retainer CW/CCW to decrease/increase activation/deactivation) and repeat cycle/test as required.
- **Record** results via `Record` (out-of-spec fields flash red, but results can still be recorded).
- **Mark part** with activation target and units (examples in WI show Torr vs PSI depending on the part).

## QAL 16 — Scorpion Calibration Check (summary)

High-level steps (single port):

- Load part, connect leads.
- **Cycle DUT**: cycle button runs **3 cycles**; `Cancel Switch Cycling` is only visible while cycling.
- Run `Precision Test` (with `Cancel Precision Test` while running).
- `Record` results; if out of spec, fields flash red and unit is set aside after recording.

## QAL 17 — Scorpion Final Test (summary)

High-level steps (single port):

- Load part, connect leads using the correct harness (work instruction lists harness mapping).
- Cycle DUT (3 cycles; cancel visible only while cycling).
- Run `Precision Test` (cancel available while running).
- Before recording, verify the serial number in software matches the product label.
- `Record` results; if out of spec, the record button turns red and the unit is identified as nonconforming.

1. **Start from safe/atmosphere**
2. **Pressurize to target/setpoint**
3. **Proof cycle** (multiple quick cycles to verify consistent behavior)
4. **Operator-gated step** (“Press Cycle” / “Cycle” / “Test”)
5. **Slow test sweep** to determine activation + deactivation points precisely
6. **Return to atmosphere/safe**
7. **Evaluate and record**

## Pressure-direction semantics

Stinger must support tests where:

- activation occurs on an **increasing** ramp and deactivation occurs on a **decreasing** ramp (common hysteresis behavior)
- the inverse is also possible depending on switch wiring and setup

The system must therefore support:

- detecting and labeling activation/deactivation edges
- associating each detected edge with “increasing” vs “decreasing” pressure direction

## Recorded outputs (per port)

Stinger records:

- measured activation pressure (increasing direction)
- measured deactivation pressure (decreasing direction)
- increasing band
- decreasing band
- reset band
- pass/fail for activation and deactivation (in-range checks)

The "band" values are the measured activation/deactivation pressures evaluated against the acceptance ranges from PTP (see `docs/03_DATABASE_SCHEMA.md` for band definitions). The database stores the core measured points (`IncreasingActivation`, `DecreasingDeactivation`) and derived gaps (`IncreasingGap`, `DecreasingGap`).

## Cancellation behavior

At any time during pressurizing/cycling/testing:

- Cancel should stop the active behavior for that port
- the port should be returned to a safe state (typically atmosphere/vent)
- partial results should be clearly marked as incomplete

