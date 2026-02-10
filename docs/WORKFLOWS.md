# Workflows (Stinger)

This document describes the operator-visible workflows Stinger supports and how they map to per-port behavior.

## Global setup (work order + parameters)

1) **Operator enters Operator ID + Shop Order**

- System loads work order context from `OrderCalibrationMaster` (PartID, SequenceID, quantity/progress as available).

2) **Verify Parameters**

- System loads PTP from `ProductTestParameters` for `(PartID, SequenceID)`.
- If missing/invalid: UI must clearly instruct the operator to report **Shop Order / Part ID / Sequence**.

## Serial numbering (per port)

Serial number is normally **auto-assigned**:

- Port A starts at `1`, Port B starts at `2`
- Each port requests “the next available serial number” when ready for a new unit
  - not already recorded in `OrderCalibrationDetail` for this Shop Order/Part/Sequence (any `ActivationID`)
  - not currently in-progress on the other port
- Operator can manually override (edit/inc/dec) to re-run a specific serial.
  - Policy: manual override begins a new “attempt window” (attempt count resets back to 1 for UI policy purposes).
 
Serial numbers are simple integers (`1`, `2`, `3`, …). The product label serial is separate and is not the “SerialNumber” field here.

## Common per-port phases (high level)

Most operations follow this general shape:

1. **Pressurize** well past the setpoint (direction depends on whether the part’s setpoint is above or below atmosphere)
2. **Operator-gated step** (QAL 15: manual SEI adjust until switch changes state)
3. **Cycle** (always 3 cycles, fast, goes far above/below setpoint)
4. **Precision test sweep**
5. **Evaluate**
6. **Record** (each attempt stored; latest attempt is authoritative)

## QAL 15 — Calibration (WCS02075 workflow detail)

### 1) Load part + pressurize

- Operator clamps the part in the port.
- Operator presses **Pressurize**.
- Port pressurizes **well above / well below** the setpoint (direction depends on part).

Buttons:

- Primary: `Pressurizing…` (disabled)
- Cancel: `Vent` (enabled)

### 2) Manual SEI adjustment (operator-gated)

- Operator twists SEI by hand until the switch **changes state** (activates or deactivates).
- **`Test` must remain disabled until the switch changes state**.

Buttons:

- Before switch change:
  - Primary: `Test` (disabled)
  - Cancel: `Vent` (enabled)
- After switch change:
  - Primary: `Test` (enabled)
  - Cancel: `Vent` (enabled)

### 3) Cycling (proof cycles)

- Operator presses `Test` (single operator action).
- The port automatically performs **3 cycles**, then immediately continues into the precision test sweep.
  - Each cycle drives far past setpoint to cycle the switch quickly.
  - A typical control strategy is to command the Alicat beyond the desired point to ramp faster through the edge.
  - After each edge (or failure to find an edge), port returns to atmosphere.

Buttons:

- Primary: `Cycling…` (disabled)
- Cancel: `Cancel Cycling` (enabled; may be shown only while cycling)

### 4) Precision test sweep

After cycling completes:

- Port goes **fast** to near the first expected edge.
- Then ramps **slowly** at a fixed sweep rate (nominally ~5 Torr/sec in vacuum contexts; converted as needed to the active units) until the first edge is detected.
- Goes a bit past, then reverses direction to capture the opposite edge.
- After both edges are captured, returns to atmosphere.

Important nuance:

- Some parts have `TargetActivationDirection = Decreasing`. In that case, the “first edge” may be the decreasing-direction switching point (activation), and the return edge may occur on the increasing direction (deactivation). Regardless of naming, Stinger must capture **one switching point on the increasing direction** and **one on the decreasing direction**, then evaluate both against their respective bands.

Buttons:

- Primary: `Testing…` (disabled)
- Cancel: `Cancel Precision Test` (enabled)

### 5) Evaluate + record

- **PASS** requires BOTH activation and deactivation to be within their respective bands.
- After evaluation:
  - PASS:
    - Confirm becomes `Record Success` (prominent/green)
    - Deny is not a retest affordance (e.g., disabled or neutral `Next`/`Clear`)
  - FAIL:
    - Stinger should reflect policy: **allow up to 3 attempts** before recording a final failure.
    - Fail attempt **1 / 2**:
      - Confirm becomes `Retest` (prominent; not green)
      - Deny becomes `Record Failure` (allowed, but not recommended)
    - Fail attempt **3 / 3**:
      - Confirm becomes `Record Failure` (prominent/green)
      - Deny becomes `Retest` (override)
    - Position rule: on attempt 3, the physical button positions swap so the **Confirm** button remains the recommended action.
- Recording writes a row to `OrderCalibrationDetail` for **every attempt** (see `DATABASE_CONTRACT.md` for `ActivationID` attempt semantics).

## QAL 16 — Calibration Check

QAL 16 verifies that the SPS (after welding the connector) still functions correctly. There is **no manual SEI adjustment** — the part was already calibrated in QAL 15.

### 1) Load part

- Operator loads part into the port, connects harness per work instruction.
- Operator presses **Test**.

Buttons:

- Primary: `Test` (enabled)
- Cancel: disabled or `Vent` if pressurized

### 2) Cycling (proof cycles)

- The port automatically performs **3 cycles** (same as QAL 15).

Buttons:

- Primary: `Cycling…` (disabled)
- Cancel: `Cancel` (enabled)

### 3) Precision test sweep

- Same behavior as QAL 15: fast approach, slow sweep at 5 Torr/sec, capture both edges.

Buttons:

- Primary: `Testing…` (disabled)
- Cancel: `Cancel` (enabled)

### 4) Evaluate + record

- Same evaluation and recording behavior as QAL 15.
- Same attempt policy (up to 3 attempts).

## QAL 17 — Final Test

QAL 17 is the final verification on top-level **170XX** part numbers. Like QAL 16, there is **no manual SEI adjustment**.

### Context

- Uses top-level **170XX** part numbers
- QAL 17 uses **SequenceID = 399** for the overwhelming majority of 170XX parts
  - DB note: `17022` also has PTP sequences `700` and `800` (confirm if those are used in production or are special cases)

### 1) Load part

- Operator loads part into the port, connects harness per work instruction.
- Operator presses **Test**.

Buttons:

- Primary: `Test` (enabled)
- Cancel: disabled or `Vent` if pressurized

### 2) Cycling (proof cycles)

- The port automatically performs **3 cycles**.

Buttons:

- Primary: `Cycling…` (disabled)
- Cancel: `Cancel` (enabled)

### 3) Precision test sweep

- Same behavior as QAL 15/16.

Buttons:

- Primary: `Testing…` (disabled)
- Cancel: `Cancel` (enabled)

### 4) Evaluate + record

- Same evaluation and recording behavior as QAL 15/16.
- Same attempt policy (up to 3 attempts).

## QAL Workflow Comparison

| Phase | QAL 15 (Calibration) | QAL 16 (Cal Check) | QAL 17 (Final Test) |
|-------|---------------------|-------------------|---------------------|
| Pressurize | Yes (manual) | No (auto on Test) | No (auto on Test) |
| Manual SEI Adjust | **Yes** | No | No |
| Wait for switch change | **Yes** | No | No |
| Proof Cycles | 3 cycles | 3 cycles | 3 cycles |
| Precision Sweep | Yes | Yes | Yes |
| Attempt Policy | 3 max | 3 max | 3 max |

## Per-port state model (button mapping)

This is a practical mapping guideline for UI text/enabled states:

- **IDLE / NEED_WO**: primary disabled (or `Verify Parameters` at system level); cancel disabled
- **READY_FOR_PRESSURIZE**: primary `Pressurize` (enabled); cancel disabled
- **PRESSURIZING**: primary `Pressurizing…` (disabled); cancel `Vent` (enabled)
- **MANUAL_ADJUST (QAL15)**:
  - before switch flip: primary `Test` (disabled); cancel `Vent` (enabled)
  - after switch flip: primary `Test` (enabled); cancel `Vent` (enabled)
- **CYCLING**: primary `Cycling…` (disabled); cancel `Cancel Cycling` (enabled)
- **PRECISION_TESTING**: primary `Testing…` (disabled); cancel `Cancel Precision Test` (enabled)
- **REVIEW**:
  - pass: confirm `Record Success` (enabled); deny not a retest affordance
  - fail:
    - attempt 1/2: confirm `Retest` (enabled); deny `Record Failure` (enabled)
    - attempt 3: confirm `Record Failure` (enabled); deny `Retest` (enabled)
- **ERROR / ABORTED**: primary `Reset` (enabled); cancel disabled

