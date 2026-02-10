# Stinger Port State Model (behavioral)

This document defines the **behavioral state model** for a single port. Port A and Port B each have their own instance.

## Port independence

- A port’s state transitions do **not** directly change the other port.
- Shared context (work order, part ID) is read-only input to a port’s behavior.

## Core states (per port)

Names here are descriptive; your implementation can choose different identifiers.

### IDLE

- No active test activity.
- Serial may be empty or ready for entry.
- Primary action: typically disabled until prerequisites are met (serial, work order, etc.).

### READY

- Serial number is loaded and prerequisites are satisfied.
- Primary action: the next operator step (often `Pressurize Port`, `Cycle DUT`, or `Precision Test`, depending on the active operation/sequence).

### PRESSURIZING

- Port is commanding pressure to a target.
- Primary action: shows activity (e.g. `Pressurizing…`) and is disabled.
- Cancel: enabled.

### PROOF_CYCLING

- Port is performing cycling intended to prove basic behavior and repeatability.
- **Always 3 cycles** (hard requirement).
- Each cycle:
  - Goes **far above (or below) setpoint** to cycle switch
  - Sets Alicat setpoint **past target setpoint** for faster ramping
  - After activation/deactivation (or if switch isn't working), returns to atmosphere
- **Purpose**: Settle mechanical components for precise reading.
- **Potential enhancement**: Use cycling to estimate rough activation/deactivation points.
- Primary action: shows activity (e.g. `Cycling…`) and is disabled.
- Cancel: enabled (shows `Cancel Cycling`, only visible while cycling).

### WAITING_FOR_OPERATOR

- Port is ready but intentionally gated by operator input.
- **QAL 15 specific**: After pressurization, operator manually adjusts SEI until switch changes state.
- **Button behavior**: 
  - Before switch state change: Primary button shows `Vent` (to exit pressurized state)
  - After switch state change: Primary button becomes enabled and shows `Test`
- Primary action: enabled only after switch state change (e.g. `Test`).
- Cancel: enabled (shows `Vent` before switch change, `Cancel` after).

### SLOW_TESTING

- Port performs a slow sweep to identify activation and deactivation points precisely.
- **Sweep behavior**:
  - Goes **fast** to a point near first activation/deactivation
  - Then **slowly ramps at ~5 torr/second** until activation
  - Goes a **little past** activation
  - Starts to come back down until deactivation occurs
  - Then returns to atmosphere
- **Debouncing**: System implements debouncing for switch edges (visualization/quantification may be enhanced).
- Primary action: shows activity (e.g. `Testing…`) and is disabled.
- Cancel: enabled (shows `Cancel Precision Test`).

### RETURNING_SAFE

- Port is returning to atmosphere/safe state and finalizing.
- Cancel: either disabled (if unsafe) or interpreted as “abort and vent now”.

### COMPLETE

- Results are available (pass/fail + bands).
- **Evaluation**: PASS requires both activation AND deactivation in range.
- **Button behavior**:
  - If PASS: Shows `Record Success` (green/prominent)
  - If FAIL: Shows `Retest` (may indicate reason: too high, too low, etc.)
- **UI guidance**: System should encourage moving on if result is success (operators tend to retry even when within limits).
- After recording: Primary action becomes `Reset` / `Clear` / `Next` for next unit.

### ERROR / ABORTED

- Hardware failure or operator cancellation.
- Port should be left safe (vent/atmosphere) and clearly show what happened.

## Events and transitions (conceptual)

Events that drive transitions:

- **operator actions**: primary action pressed, cancel pressed, serial edited
- **hardware conditions**: target reached, edge detected (activation/deactivation), comm loss
- **timing conditions**: timeouts (optional; define only if real)

## Mapping state → button text (guideline)

The label should communicate “next action” or “current activity”:

- READY → `Pressurize` (or whatever the next step is)
- PRESSURIZING → `Pressurizing…`
- PROOF_CYCLING → `Cycling…`
- WAITING_FOR_OPERATOR → `Cycle` or `Test`
- SLOW_TESTING → `Testing…`
- COMPLETE → `Reset` / `Next`

### Known operator-visible labels (from work instructions)

These labels are known to exist in the current LabVIEW workflow and are useful anchors for the PyQt rewrite:

- `Verify Parameters`
- `Start Calibration`
- `Pressurize Port`
- `Cycle` / `Cycle DUT`
- `Cancel Switch Cycling`
- `Precision Test`
- `Cancel Precision Test`
- `Record` / `Record Success` / `Record Failure`
