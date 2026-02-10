# Stinger Knowledge Consolidation

This document consolidates key findings and answers from exploration and user feedback.

## Quick Reference

### Test Pass Criteria
- **PASS**: Both activation AND deactivation must be within their respective bands
- **FAIL**: Either activation or deactivation out of range, or other failure modes

### QAL 17 Sequence Pattern
- QAL 17 Final Test uses **SequenceID=399** for all 170XX parts
- Confirmed for: 17029, 17036, 17025, 17088, and 58 total 170XX parts
- 17030 does NOT have PTP entries (as expected)

### Pressure Control Architecture
- **Alicat**: Control (not rated for torr precision)
- **Transducer**: Measurement/recording (rated for +/- 1.4 torr)
- **Solenoid**: Switches exhaust between atmosphere and vacuum
- **Complex interaction**: When controlling vacuum and needs to come up, switches to atmosphere for exhaust

### Proof Cycling
- **Always 3 cycles**
- Goes far above/below setpoint
- Sets Alicat setpoint past target for faster ramping
- **Purpose**: Settle mechanical components
- **Enhancement idea**: Use cycling to estimate rough activation/deactivation points

### Slow Test Sweep
- **Rate**: ~5 torr/second
- **Behavior**: Fast to near first edge → slow ramp to activation → little past → back down to deactivation → return to atmosphere
- **Debouncing**: Implemented (visualization may be enhanced)

### Serial Number Management
- Auto-increment: Port A starts at 1, Port B at 2
- Assigns next available serial number (not tested or not currently testing)
- Manual override: Operator can enter/increment/decrement to go back

### Shop Order Auto-Fill
- Operator enters Shop Order
- System queries `OrderCalibrationMaster` to auto-fill:
  - Part ID
  - Sequence ID (`LastSequenceCalibrated`)
  - Quantity (`OrderQTY`)

### Database Tables
- **Read**: `OrderCalibrationMaster` (shop order info), `ProductTestParameters` (test parameters - key-value table)
- **Write**: `OrderCalibrationDetail` (per-part results)
- **Retest**: Overwrites last entry for same serial number

### Units of Measure
- **PTP**: Stores numeric codes (Alicat internal codes: 0=Default, 1=Unknown, 10=PSI, 19=cmH2O, 21=inH2O, etc.)
- **OrderCalibrationDetail**: Stores strings (PSIG, TORR, INHG, etc.)
- **Display**: Graph and indicators show units matching part being tested

### Graph Scaling
- Scale per part (dynamic)
- Scale from atmosphere to farthest most limit (increasing/decreasing high/low)
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
6. **Slow precision test** → Fast to near edge → 5 torr/sec ramp → activation → past → back down → deactivation → atmosphere
7. **Evaluate** → PASS (both in range) or FAIL (retest)
8. **Record** → Save to `OrderCalibrationDetail` (overwrites if retest)

## Remaining Questions

See `90_OPEN_QUESTIONS.md` for remaining technical questions:
- Gap fields meaning (`IncreasingGap`, `DecreasingGap`)
- UOM code to string conversion
- Solenoid output count per port
- Audible cues
- Top 5 admin data points
