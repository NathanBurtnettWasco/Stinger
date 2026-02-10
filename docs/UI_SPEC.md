# UI Spec (Stinger)

This document describes the operator-facing UI behaviors and the key interaction patterns Stinger must support.

## Design goals

- **Touch-first**: large targets (44px+), minimal precision clicking
- **Always answers “what do I do next?”** per port
- **Two-port mental model**: Port A and Port B as two independent columns
- **Meaningful color**: success/fail/disabled states should be obvious at a glance
- **No audio**: no beeps/sounds (cleanroom)

## Screen structure

Stinger has three primary areas:

- **Main**: production workflow
- **Debug**: manual controls per port (independent of PTP/work order)
- **Admin**: system observability (hardware + DB + state/history)

## Main tab layout

### Top bar (shared)

Top bar contains:

- **End Work Order / End Calibration**
- **Work order card**: Operator ID, Shop Order, Part ID, Sequence, progress (optional)
- **Close Program**

### Port columns (Port A / Port B)

Each port column contains:

- **Serial number control**
  - normally auto-assigned; operator can manually override (edit/inc/dec)
- **Pressure**
  - large numeric readout + unit label (unit comes from PTP/UOM)
- **Vertical “1D” pressure visualization**
  - atmosphere reference
  - current pressure marker
  - activation/deactivation acceptance windows (“bands”)
  - optional markers for measured activation/deactivation points
  - scale behavior: dynamic per part; typically from atmosphere to the farthest test limit
- **Results-at-a-glance**
  - activation + deactivation result (in/out of range)
  - optional display of band limits
- **Two large buttons**
  - Confirm (dynamic label)
  - Deny (dynamic label)

## Button behavior (critical)

### Two-button model (per port): Confirm / Deny

- **Confirm button**: the next recommended operator action for that port (dynamic label + enabled/disabled)
  - **Color rule**: Confirm should **not** be green during the active test phases; reserve **green** for the **end-of-attempt record action** (see Anti-retest UX).
- **Deny button**: context-sensitive “get out / stop / alternate choice” action
  - During active test phases, Deny is typically `Vent` / `Cancel`.
  - In review states, Deny may represent “the other choice” (e.g., `Record Failure` vs `Retest`).

### QAL 15 gating example (manual SEI adjust)

After pressurization, the operator must manually twist the SEI until the switch changes state:

- Before switch change:
  - Primary action: **`Test`** (disabled)
  - Cancel: **`Vent`** (enabled)
- After switch change:
  - Primary action: **`Test`** (enabled)
  - Cancel: **`Vent`** (enabled)

### Running states (examples)

- Pressurizing: primary shows `Pressurizing…` and is disabled; cancel shows `Vent`
- Cycling: primary shows `Cycling…` and is disabled; cancel shows `Cancel Cycling` (optional visibility-only-while-cycling behavior)
- Testing: primary shows `Testing…` and is disabled; cancel shows `Cancel Precision Test`

### Anti-retest UX (production reality)

Operators may try to “dial it in dead-on” even when already in range. To reduce this:

- When PASS:
  - Confirm becomes **`Record Success`** (green/prominent)
  - Deny should not encourage retesting (e.g., disabled, or a neutral `Next`/`Clear` action if needed)
- When FAIL:
  - Stinger should reflect policy: **allow up to 3 attempts** before recording a final failure.
  - FAIL attempts are still recorded (even when the operator chooses `Retest`) so the attempt history is preserved.
  - Fail attempt **1 / 2**:
    - Confirm becomes **`Retest`** (prominent; **not green**)
    - Deny becomes **`Record Failure`** (allowed, but not recommended)
  - Fail attempt **3 / 3**:
    - Confirm becomes **`Record Failure`** (prominent / green)
    - Deny becomes **`Retest`** (override)
  - **Position swap rule**: on attempt 3, swap which physical button shows `Retest` vs `Record Failure` so the **Confirm** button remains the recommended action.

## Debug tab (scope)

Debug is intended to be **highly capable** for engineering use:

- per-port setpoint + ramp rate controls
- solenoid routing control
- manual “mini sweep” (engineering-only precision sweep) for troubleshooting
- live transducer pressure display
- live NO/NC switch state display
- edge capture history (with timestamps + pressure)

### Debug/Admin access guardrail

Debug and Admin should be protected by a simple PIN prompt to avoid accidental use in production.

- Default PIN: **2245**

## Admin tab (scope)

Admin is read-only and should be **organized** (collapsible groups):

- **Hardware**: per-port Alicat status + last command/readback; DAQ status; DI/DO states
- **Database**: connection status; last read/write; last error summary
- **Database history**: last N writes (key fields + pass/fail) for quick audit
- **System**: version, uptime, logs

## Proven UI patterns to reuse (from other stands)

Stinger should reuse established Wasco patterns seen in `Functional Stand` and `Micro Tester`:

- **UI bridge / mediator** pattern: UI updates are driven by state + data (not ad-hoc widget logic)
- **Button lockout** (brief) to prevent double-tap/double-trigger on touch screens
- **Graceful stop + timeout**: if stopping takes too long, show escalating warnings and offer a forced stop

