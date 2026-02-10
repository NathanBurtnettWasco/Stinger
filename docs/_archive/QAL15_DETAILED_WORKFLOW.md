# QAL 15 Detailed Workflow (WCS02075 Test Stand)

This document describes the detailed operator workflow for QAL 15 Scorpion Calibration on the Stinger test stand.

## Initial Setup

1. **Load work order context**: Operator enters Shop Order, which auto-fills:
   - Part ID (from `OrderCalibrationMaster`)
   - Sequence ID (from `OrderCalibrationMaster`)
   - Quantity (from `OrderCalibrationMaster`)
   - Operator ID (manual entry)

2. **Verify Parameters**: System loads test parameters from `ProductTestParameters` table based on PartID and SequenceID.

## Per-Port Workflow (QAL 15)

### 1. Load Part and Pressurize

- Operator loads part into test port and tightens it down
- Operator presses **"Pressurize"** button
- System pressurizes port **well above or well below setpoint** (depends on whether part is pressure or vacuum side of atmosphere)
- **Button state**: Shows "Pressurizing..." and is disabled
- **Cancel button**: Enabled, shows "Vent" — allows operator to exit pressurized state

### 2. Manual SEI Adjustment (Operator-Gated)

- Operator manually twists the SEI (Sub Electrical Interface) until switch **activates or deactivates**
- UI shows switch state change (micro-switch indicator changes)
- **Button state**: 
  - Before switch state change: Primary button shows "Vent" (to exit pressurized state)
  - After switch state change: Primary button becomes enabled and shows **"Test"**
- **Test button is NOT active until switch changes state**

### 3. Proof Cycling

- Operator presses **"Test"** button
- **Button state**: Changes to "Cycling..." and is disabled
- System automatically performs **3 proof cycles**:
  - Each cycle goes **far above (or below) the setpoint** to cycle the switch
  - System sets Alicat setpoint **past the target setpoint** to ramp faster through the activation/deactivation point
  - After activation/deactivation (or if switch isn't working), returns to atmosphere
  - **Purpose**: Settle mechanical components for precise reading
  - **Potential enhancement**: Use cycling to estimate rough activation/deactivation points for faster slow ramp positioning

- **Cancel button**: Enabled, shows "Cancel Cycling" (only visible while cycling)

### 4. Slow Precision Test Sweep

- After proof cycling completes:
  - System goes **fast** to a point near the first activation/deactivation
  - Then **slowly ramps at ~5 torr/second** until it hits activation
  - Goes a **little past** activation
  - Starts to come back down until deactivation occurs
  - Then returns to atmosphere

- **Button state**: Shows "Testing..." and is disabled
- **Cancel button**: Enabled, shows "Cancel Precision Test"

### 5. Result Evaluation

- System evaluates results:
  - **PASS**: Both activation AND deactivation are within their respective bands
  - **FAIL**: Either activation or deactivation is out of range, or other failure modes

- **Button state**: 
  - If PASS: Shows "Record Success" (green/prominent)
  - If FAIL: Shows "Retest" (may indicate reason: too high, too low, etc.)

- **UI behavior**: 
  - System should **encourage moving on** if result is a success (operators tend to retry even when within acceptable limits)
  - Out-of-spec fields may flash red, but results can still be recorded

### 6. Recording Results

- Operator presses "Record Success" or "Retest"
- System saves to `OrderCalibrationDetail` table:
  - `IncreasingActivation`: Measured activation pressure (increasing direction)
  - `DecreasingDeactivation`: Measured deactivation pressure (decreasing direction)
  - `IncreasingGap`: Gap value (often 0.000)
  - `DecreasingGap`: Gap value (often 0.000)
  - `InSpec`: Pass/fail bit
  - `UnitsOfMeasure`: String value (converted from PTP UOM code)

- **Retest behavior**: If operator chooses "Retest", system allows retesting the same serial number (overwrites previous entry)

### 7. Serial Number Management

- **Auto-increment**: Serial numbers start at 1 for Port A, 2 for Port B
- System assigns next available serial number that hasn't been tested or isn't currently being tested
- Ports may be running at different speeds, so serial numbers are assigned dynamically
- **Manual override**: Operator can manually enter or increment/decrement serial number to go back

## Pressure Control Details

### Alicat + Transducer Architecture

- **Alicat**: Used for **control** (not rated for torr-level precision but used for control)
- **Transducer**: Used for **measurement/recording** (rated for +/- 1.4 torr accuracy)
  - 0.5-4.5V ratiometric transducer
  - Connected via LabJack T7-Pro
  - Noise levels may vary by installation

- **Alicat pressure control**:
  - Pressure port: Always pressurized high
  - Exhaust port: Connected to solenoid
  - Solenoid switches between:
    - **Atmosphere**: For exhausting back up (when controlling pressure in vacuum and needs to come up)
    - **Vacuum**: For pulling down

- **Complex interaction**: When switch is controlling pressure in vacuum and wants to come up, it can still control but needs to switch back to atmosphere for the relay to exhaust back up.

## Pressure Units and Display

- **Units**: Graph and all indicators show units matching the part being tested (PSI, Torr, PSIA, PSIG, inH2O, etc.)
- **Graph scaling**: 
  - Scale per part (dynamic)
  - Previously scaled from **atmosphere to the farthest most limit** (increasing/decreasing high/low)
  - This makes it easier to see how close activation/deactivation was to setpoint
  - May want to explore scaling during test (maybe not)

## Debouncing

- System implements debouncing for switch edges
- **Future enhancement**: Better visualization and quantification of debouncing behavior (was difficult to see in LabVIEW)

## Digital Inputs

- **DB9 connector**: Up to 9 digital inputs per port
- **NO/NC**: Switch states (can be HIGH or LOW depending on switch configuration)
- **No watchdog**: Watchdog is only in Functional Stand, not Stinger
