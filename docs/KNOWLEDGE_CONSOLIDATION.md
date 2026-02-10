# Stinger Knowledge Consolidation

This document consolidates key findings and answers from exploration and user feedback.

## Quick Reference

### Test Pass Criteria
- **PASS**: Both activation AND deactivation must be within their respective bands
- **FAIL**: Either activation or deactivation out of range, or other failure modes

### QAL Workflow Types

| QAL | Name | Operation | Has Manual SEI? |
|-----|------|-----------|-----------------|
| QAL 15 | Calibration | Calibrate SPS (Scorpion with electrical) | **Yes** |
| QAL 16 | Calibration Check | Verify after welding connector | No |
| QAL 17 | Final Test | Top-level 170XX part verification | No |

- **QAL 15**: Full calibration with manual SEI adjustment step
- **QAL 16/17**: Verification only — just cycle + precision test, no manual step

### QAL 17 Sequence Pattern
- QAL 17 Final Test uses **SequenceID=399** for all 170XX parts
- Confirmed for: 17029, 17036, 17025, 17088, and 58 total 170XX parts
- 17030 does NOT have PTP entries (as expected)

### Part Assembly Flow
```
SWA (Sub Welded Assembly)
    ↓ add bevel spring
SBA (Sub Body Assembly) — calibrated to activate at setpoint
    ↓ add electrical
SPS — QAL 15 (calibration) and QAL 16 (cal check)
    ↓ 
170XX (Top Level) — QAL 17 (final test)
```

### Pressure Control Architecture
- **Alicat**: Control (not rated for torr-level precision, but used for closed-loop ramping)
- **Transducer**: Measurement/recording authority (0.5-4.5V = 0-115 PSI)
- **Solenoid**: Switches exhaust between atmosphere and vacuum
- **Complex interaction**: When controlling in vacuum and needs to rise, switch to atmosphere for exhaust

### Control Rates
- **Precision sweep**: 5 Torr/second
- **Fast ramp**: Set Alicat setpoint to 0 (or max) — controller slews as fast as possible

### Proof Cycling
- **Always 3 cycles**
- Goes far above/below setpoint (farthest PTP limit from atmosphere, excluding ±Inf)
- Sets Alicat setpoint past target for faster ramping
- **Purpose**: Settle mechanical components before precision measurement
- **Failure mode**: If no edge within 10% past limit, return and error

### Precision Test Sweep
- **Rate**: 5 Torr/second
- **Behavior**: Fast to near first edge → slow ramp → detect activation → slight overshoot → reverse → detect deactivation → return to atmosphere
- **Debouncing**: Capture first transition, require N stable samples to confirm

### Serial Number Management
- Auto-increment: Port A starts at 1, Port B at 2
- Assigns next available serial number (not already tested, not in-progress on other port)
- Manual override: Operator can enter/increment/decrement to re-run
- **Thread safety**: Use lock for serial allocation to prevent race between ports

### Shop Order Auto-Fill
- Operator enters Shop Order
- System queries `OrderCalibrationMaster` to auto-fill:
  - Part ID
  - Sequence ID (`LastSequenceCalibrated`)
  - Quantity (`OrderQTY`)

### Database Tables
- **Read**: `OrderCalibrationMaster` (work order context), `ProductTestParameters` (test parameters - key-value table)
- **Write**: `OrderCalibrationDetail` (per-unit results)
- **Retest behavior**: **UPDATE** the existing row (overwrites in place)

### Units of Measure
- **PTP**: Stores numeric codes (to be mapped via enum — TBD)
- **OrderCalibrationDetail**: Stores unit strings (PSI, INHG, Torr, mmHg @ 0° C, etc.)
- **Display**: Graph and indicators show units matching part being tested
- **Status**: UOM mapping is pending resolution

### Graph Scaling
- Scale per part (dynamic)
- Range: atmosphere to farthest test limit (not ±Inf)
- Makes it easier to see how close activation/deactivation was to setpoint

### Band Definitions
- **Increasing band**: `IncreasingLowerLimit` to `IncreasingUpperLimit` (may use `-Inf`)
- **Decreasing band**: `DecreasingLowerLimit` to `DecreasingUpperLimit` (may use `Inf`)
- **Reset band**: `ResetBandLowerLimit` to `ResetBandUpperLimit` (often `-Inf` to `Inf`)

## QAL 15 Workflow Summary

1. **Load work order** → Auto-fills Part ID, Sequence, Quantity
2. **Load part** → Tighten down, pressurize (well above/below setpoint)
3. **Manual SEI adjustment** → Twist until switch changes state
4. **Test button activates** → Press "Test"
5. **Proof cycling** → 3 cycles automatically (fast, far above/below setpoint)
6. **Slow precision test** → Fast to near edge → 5 Torr/sec ramp → activation → past → back down → deactivation → atmosphere
7. **Evaluate** → PASS (both in range) or FAIL
8. **Record** → Save to `OrderCalibrationDetail` (new row with ActivationID)

## QAL 16/17 Workflow Summary

1. **Load work order** → Auto-fills Part ID, Sequence, Quantity
2. **Load part** → Connect harness (per work instruction)
3. **Press "Test"** → (no manual SEI step)
4. **Proof cycling** → 3 cycles automatically
5. **Slow precision test** → Same as QAL 15
6. **Evaluate** → PASS or FAIL
7. **Record** → Save to `OrderCalibrationDetail`

## Hardware Summary

### DAQ Configuration
- **Port A (Left)**: LeftDAQ
- **Port B (Right)**: RightDAQ
- **Transducer**: 0.5-4.5V ratiometric = 0-115 PSI

### Alicat Configuration
- **COM Port**: COM3 (default)
- **Port A (Left)**: Address B
- **Port B (Right)**: Address A

### Solenoid Truth Table
- `DO = 1` → **Vacuum** (pull down)
- `DO = 0` → **Atmosphere** (safe default)

## Remaining Questions

See `OPEN_QUESTIONS.md` for remaining technical questions:
- Gap fields meaning (`IncreasingGap`, `DecreasingGap`)
- UOM code-to-string mapping (pending)
- Exact DI pin assignments for NO/NC per port
