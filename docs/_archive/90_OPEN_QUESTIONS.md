# Stinger Open Questions

This list tracks remaining questions and clarifications needed for implementation.

## A) Test meaning and math

- ✅ **Band definitions** (ANSWERED): See `03_DATABASE_SCHEMA.md`
- ✅ **PASS criteria** (ANSWERED): Both activation AND deactivation must be in range
- What does `InSpec` bit in `OrderCalibrationDetail` represent exactly? (likely: activation in range AND deactivation in range)

## B) Per-port workflow (operator actions)

- ✅ **QAL 15 workflow** (ANSWERED): See `QAL15_DETAILED_WORKFLOW.md`
- ✅ **Operator-gated steps** (ANSWERED): 
  - After pressurization, operator manually adjusts SEI until switch changes state
  - Test button only becomes active after switch state change
- ✅ **Cancel behavior** (ANSWERED): 
  - Before switch change: Shows "Vent" to exit pressurized state
  - During cycling/testing: Cancels current operation and returns to safe state
  - Partial results: Discarded on cancel (not saved)

## C) Pressure units and scaling

- ✅ **UOM mapping** (ANSWERED): See `03_DATABASE_SCHEMA.md` and `DATABASE_EXPLORATION_SUMMARY.md`
- ✅ **Display units** (ANSWERED): Graph and indicators show units matching part being tested (PSI, Torr, PSIA, PSIG, inH2O, etc.)
- ✅ **Graph scaling** (ANSWERED): 
  - Scale per part (dynamic)
  - Scale from atmosphere to farthest most limit (increasing/decreasing high/low)
  - May explore scaling during test (maybe not)
- How do we convert from PTP UOM codes to string format used in `OrderCalibrationDetail`?

## D) Hardware truth table (per port)

- ✅ **Current pressure source** (ANSWERED): 
  - **Alicat**: Used for control (not rated for torr-level precision)
  - **Transducer**: Used for measurement/recording (rated for +/- 1.4 torr accuracy)
- Transducer: 0.5-4.5V ratiometric, connected via LabJack T7-Pro
  - Noise levels have been challenging (may be DAQ-related)
- ✅ **Digital inputs** (ANSWERED): 
  - DB9 connector: Up to 9 digital inputs per port
  - NO/NC: Switch states (can be HIGH or LOW)
  - No watchdog (watchdog is only in Functional Stand)
- ✅ **Solenoids** (ANSWERED): 
  - Alicat exhaust port connected to solenoid
  - Solenoid switches between atmosphere and vacuum
  - Complex interaction: When controlling pressure in vacuum and wants to come up, switches to atmosphere for relay to exhaust back up
- How many solenoid outputs per port? (likely 1 per port for exhaust control)

## E) Proof cycling details

- ✅ **Number of cycles** (ANSWERED): Always 3 cycles
- ✅ **Cycle definition** (ANSWERED): 
  - Goes far above (or below) setpoint to cycle switch
  - Sets Alicat setpoint past target setpoint for faster ramping
  - After activation/deactivation (or if switch isn't working), returns to atmosphere
- ✅ **Purpose** (ANSWERED): Settle mechanical components for precise reading
- ✅ **Potential enhancement** (ANSWERED): Use cycling to estimate rough activation/deactivation points for faster slow ramp positioning (may be bad idea, needs experimentation)

## F) Slow sweep details

- ✅ **Sweep behavior** (ANSWERED): 
  - Goes fast to point near first activation/deactivation
  - Slowly ramps at ~5 torr/second until activation
  - Goes a little past activation
  - Starts to come back down until deactivation occurs
  - Then returns to atmosphere
- ✅ **Completion criteria** (ANSWERED): After both activation + deactivation captured, returns to atmosphere
- ✅ **Debouncing** (ANSWERED): System implements debouncing (visualization/quantification may be enhanced)

## G) Main UI specifics

- ✅ **Serial number entry** (ANSWERED): 
  - Auto-increment: Starts at 1 for Port A, 2 for Port B
  - Assigns next available serial number that hasn't been tested or isn't currently being tested
  - Manual override: Operator can manually enter or increment/decrement to go back
- ✅ **Required fields** (ANSWERED): 
  - Operator ID (manual entry)
  - Shop Order (manual entry, auto-fills Part ID, Sequence ID, Quantity from `OrderCalibrationMaster`)
  - Part ID (auto-filled)
  - Sequence ID (auto-filled)
  - Quantity (auto-filled, not strictly required but ideal)
- Any audible cues (pass/fail beep)? (not specified)

## H) Debug tab scope

- ✅ **Debug capabilities** (ANSWERED): 
  - Full configurability and ease of use desired
  - Should allow testing switches in very custom ways
  - Per port: setpoint + ramp rate, solenoid control, relay control, live switch state + edge capture, independent parameters (not PTP-driven)

## I) Admin tab scope

- ✅ **Current LabVIEW admin data** (ANSWERED): 
  - PTP info, shop order info, calibration data, state indicators, serial numbers, all Alicat data, micro switch state history, etc.
- Should this be simplified? (user says "maybe maybe not")
- What are the top 5 "must show" data points for day-to-day use?

## J) Database contract

- ✅ **Tables** (ANSWERED): 
  - Read: `OrderCalibrationMaster` (shop order info), `ProductTestParameters` (test parameters)
  - Write: `OrderCalibrationDetail` (per-part results)
- ✅ **Progress tracking** (ANSWERED): Count of saved results (can query `OrderCalibrationDetail` by ShopOrder)
- ✅ **Retest behavior** (ANSWERED): Can retest any part, overwrites last entry for that serial number

## K) Work order routing vs PartID naming

- ✅ **17030** (ANSWERED): `17030` does not have PTP entries; other 170XX parts (17029, 17036, 17025, 17088, etc.) have PTP entries with `SequenceID=399` (QAL 17 Final Test)
- ✅ **QAL 17 storage** (ANSWERED): QAL 17 is stored under 170XX parts with SequenceID=399 (always)
- How do we determine which `PartID` to query for PTP when a work order references a top-level assembly like `17030`? (may need to look up underlying switch PartID)

## L) Remaining technical questions

- What do the "Gap" fields (`IncreasingGap`, `DecreasingGap`) represent? They're often 0.000 in the data.
- How do we convert from PTP UOM codes to string format used in `OrderCalibrationDetail`?
- How many solenoid outputs per port? (likely 1 for exhaust control)
- Any audible cues for pass/fail?
- What are the top 5 "must show" admin data points?
