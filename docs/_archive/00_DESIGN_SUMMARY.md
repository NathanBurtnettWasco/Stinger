# Stinger System Specification (Authoritative)

This documentation describes **what Stinger is** and **how it behaves** (operator workflow, UI behavior, hardware, data). It intentionally avoids project planning, roadmaps, and “next steps”.

## Purpose

Stinger is a **dual-port pressure switch test stand** used in a **cleanroom** with **high purity N₂** to test the **Scorpion** product line. Each port runs independently with its own:

- Alicat pressure controller
- Solenoid(s) for routing/venting
- Digital inputs to read the micro-switch state

Both ports share the same application instance and operator/work order context.

## Production context (work order / routing)

For Scorpion parts (example `SPS01414-03`), the stand is used across multiple work order operations, including:

- **QAL 15**: install SEI (sub electrical) + calibration workflow
- **QAL 16**: calibration check workflow
- **QAL 17**: final test workflow (top-level stage, harness-specific)

The operational behavior is driven by **Work Order + Sequence** and corresponding **PTP** rows.

## What operators see (high-level)

Stinger has three primary UI areas:

- **Main**: operator-facing production workflow (touch-first)
- **Debug**: manual controls per port (ignores/overrides normal parameter flow)
- **Admin**: read-only/system-observability (hardware + DB + system manager data)

## Core UI concepts (first-principles)

### 1) Two independent ports

- Port A and Port B are **independent state machines**.
- Starting/canceling one port does **not** implicitly start/cancel the other (unless explicitly designed as a safety behavior).

### 2) Two primary buttons per port (touch-friendly)

Each port has two prominent buttons:

- **Primary “do something” button**: the next valid operator action for that port.
  - Label and enabled/disabled state are dynamic.
  - Examples: `Pressurize`, `Cycle`, `Test`, `Pressurizing…`, `Cycling…`, `Testing…`
- **Cancel button**: aborts the current port operation and returns the port to a safe/idle-ish condition.

### 3) High-density vertical pressure visualization (per port)

Each port shows a **vertical, 1D pressure visualization** (not primarily a time-series plot). It communicates, at a glance:

- current pressure
- atmosphere reference
- target / setpoint context
- activation + deactivation context (zones/lines)
- acceptable ranges for activation/deactivation (pass windows)

### 4) “Results-at-a-glance” fields (per port)

Each port shows numeric results from the test (as you described):

- **Increasing band**
- **Decreasing band**
- **Reset band**

*(Exact definitions and how they map to activation/deactivation logic are captured in `docs/90_OPEN_QUESTIONS.md` until confirmed.)*

## Main page layout (from the LabVIEW screenshot, adapted for a modern PyQt UI)

### Top bar (shared)

Top bar contains:

- **End calibration / end work order** action (left)
- **Work order details** (center): operator ID, shop order, sequence, part ID, quantity/progress
- **Close program** action (right)

### Port columns (left = Port A, right = Port B)

Each port column contains:

- serial number input/control
- pressure indicator (numeric + visual)
- vertical pressure graph/indicator with ranges/zones
- the three result fields (increasing/decreasing/reset band)
- the two large buttons (primary action + cancel)

## Test lifecycle (conceptual)

Per port, the system performs a multi-step test that includes:

- pressurizing to a target/setpoint
- a fast “proof/cycle” behavior (multiple quick cycles)
- an operator-gated step (“press cycle” / “cycle” / similar)
- a slow sweep to detect and record activation/deactivation points with precision
- return to atmospheric / safe state
- evaluate pass/fail and record results

The detailed behavioral definition lives in:

- `docs/06_TEST_SEQUENCES.md` (sequence narrative)
- `docs/05_STATE_MACHINE.md` (state model + button behavior mapping)

## Non-goals (intentionally excluded)

- “Future vision” scaling (5–10 ports), robots, message queues, dashboards
- project plans/phases/milestones
- speculative features not directly tied to current Stinger operation

