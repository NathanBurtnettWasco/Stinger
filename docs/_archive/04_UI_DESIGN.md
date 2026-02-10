# Stinger UI Design (descriptive)

This document describes the UI behaviors Stinger must support, based on the LabVIEW layout you shared and the interaction patterns used in `Functional Stand` and `Micro Tester`.

## Design goals

- **Touch-first**: big targets, minimal precision tapping
- **Operator clarity**: the UI always answers “what do I do next?” per port
- **Context-first**: color and layout convey meaning without reading paragraphs
- **Two-port mental model**: operators think in Port A and Port B columns

## Screen structure

Stinger has three main tabs:

- **Main**: production workflow
- **Debug**: manual controls per port (independent of PTP/work order flow)
- **Admin**: system observability (hardware + data sources)

## Main tab layout

### Top bar (shared)

- **Left**: End Work Order / End Calibration (confirm intent; exact wording TBD)
- **Center**: Work order card (operator, shop order, sequence, part ID, quantity/progress)
- **Right**: Close Program (requires confirmation)

### Port columns (Port A and Port B)

Each port column includes:

- **Serial number control**
  - fast entry (keyboard or scanner)
  - clear “loaded vs not loaded” affordance
- **Pressure indicator**
  - numeric pressure (large)
  - optional small units label (always visible)
- **Vertical pressure visualization**
  - atmospheric reference
  - current pressure
  - target/setpoint reference(s)
  - acceptable activation/deactivation ranges (zones)
- **Result fields**
  - increasing band
  - decreasing band
  - reset band
- **Two large buttons**
  - primary action button (dynamic label)
  - cancel button (always present; enabled only when cancel is meaningful)

### Common “database gating” affordance

In the existing LabVIEW workflow, operators explicitly tap **Verify Parameters** after entering operator + work order context. If parameters cannot be found, the UI must clearly instruct the operator to report **Work Order, Part ID, and Sequence Number**.

## Button behavior (critical UX)

Per port:

- **Primary action button**
  - enabled only when the operator has a valid “next step”
  - label changes to reflect the next step or current activity
  - examples:
    - idle/ready: `Pressurize`, `Cycle`, `Test`
    - running: `Pressurizing…`, `Cycling…`, `Testing…`
- **Cancel**
  - aborts the current operation for that port
  - leaves the port in a safe state (typically vent/atmosphere and “not running”)

### Visibility nuance from the work instructions

Some cancel buttons are only visible while an operation is active (example from the work instructions: `Cancel Switch Cycling` is only visible while cycling is occurring). We can replicate this pattern if it improves clarity, or keep Cancel always-visible but disabled.

## Debug tab (redo from scratch)

Debug exists to control hardware regardless of PTP/work order:

- per-port setpoint control
- per-port ramp rate control
- per-port solenoid control
- per-port relay/outputs control (if applicable)
- live micro-switch state display
- live activation/deactivation edge capture (timestamps + pressures)

## Admin tab (simplify)

Admin is read-only and grouped into collapsible sections, e.g.:

- **Hardware**
  - Port A: Alicat status + latest readback + comm state
  - Port B: Alicat status + latest readback + comm state
  - DAQ: device status + last sample time + DI states
- **Database**
  - connection state
  - last read/write timestamps
  - last error summary
- **System**
  - app version, config version, uptime, logs

