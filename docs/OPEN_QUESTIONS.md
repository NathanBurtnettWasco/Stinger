# Open Questions (remaining)

This list exists to keep unknowns explicit and actionable (so we don't "fill in" details that must match reality).

## ✅ Recently Resolved

These items have been answered and documented:

- **Alicat addresses**: Port A (Left) = Address B, Port B (Right) = Address A, both on COM3
- **DAQ device names**: LeftDAQ (Port A), RightDAQ (Port B)
- **Transducer scaling**: 0.5-4.5V = 0-115 PSI
- **Solenoid truth table**: DO=1 → Vacuum, DO=0 → Atmosphere
- **Left solenoid channel**: `LeftDAQ/port1/line3`
- **Control rates**: Precision sweep = 5 Torr/sec, Fast = set to 0/max
- **Proof cycling**: Always 3 cycles
- **Edge failure behavior**: Go 10% past limit, then return and error
- **QAL 16/17 workflow**: Same as QAL 15 but without manual SEI adjustment step
- **Retest behavior**: Insert new row with incremented ActivationID
- **Sequence ID format**: Use 399 (not 0399) for display

---

## 🔴 Hardware / IO Mapping (blocking)

Must be confirmed before building hardware layer:

### Transducer AI Channels
- **Port A (Left)**: Which AI channel? (e.g., `LeftDAQ/ai0`?)
- **Port B (Right)**: Was noted as `RightDAQ/ai1:2` — does this mean:
  - `ai1` is the transducer channel?
  - `ai1:2` is a differential pair?
  - Something else?

### DI Pin Assignments for NO/NC
- Pin mapping is known: Pin 1 = `port0/line0`, Pin 2 = `port0/line1`, etc.
- **Still need**: Which specific pins are wired to:
  - Port A NO terminal
  - Port A NC terminal
  - Port B NO terminal
  - Port B NC terminal

### DO Channel for Right Solenoid
- Left confirmed: `LeftDAQ/port1/line3`
- **Still need**: What is the Right solenoid channel? (e.g., `RightDAQ/port1/line3`?)

---

## 🟡 Database: remaining unknowns

### Gap fields meaning
- What do `OrderCalibrationDetail.IncreasingGap` and `OrderCalibrationDetail.DecreasingGap` represent?
- Evidence from the DB:
  - For SPS parts, these fields are almost always 0 (only a tiny number of legacy rows have non-zero values).
  - We did not find an obvious formula that matches the non-zero values.
- **Decision**: Stinger will write `0` for both gap fields until clarified.

### Units of Measure mapping
- PTP stores numeric codes → `OrderCalibrationDetail` stores string values
- Known mappings documented in `DATABASE_CONTRACT.md`
- **Status**: Marked as TBD; will resolve as an enum when full mapping is confirmed
- **Fallback behavior**: If unknown code encountered, log warning and write raw value

---

## 🟡 Measurement behavior (tune on hardware)

These will be refined during commissioning:

### Debounce tuning
- Starting values in `stinger_config.yaml`:
  - Stable sample count: 3
  - Min edge interval: 50 ms
- Will tune based on observed switch behavior

### Transducer noise
- LabJack T7-Pro noise characteristics need validation on the stand
- May need:
  - Software filtering / averaging
  - Hardware shielding improvements
- Initial approach: Average N samples per read (configurable)

### Vacuum switching threshold (pump protection)
- Suggested initial value: 5 PSI
- **Confirm**: Is this conservative enough? Should we require blowdown to atmosphere before switching?

---

## 🟡 Workflow details (low priority)

### QAL 17 sequence exceptions
- Most 170XX parts use `SequenceID=399`
- `17022` also has `700` and `800` in PTP
- **Confirm**: Are those sequences ever used in production, or are they special cases?

---

## 🔵 Future / Stretch

### Offline mode
- If we implement offline support, confirm:
  - What is the allowed offline workflow (read-only parameters vs full test+record)?
  - How should merge conflicts be handled if the same unit/attempt exists both locally and in SQL Server?

### Debug tab features
- Mini-sweep functionality
- Debounce visualization
- Edge history display
- Exact parameters TBD during development
