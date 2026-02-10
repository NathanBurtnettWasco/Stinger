# Database Exploration Notes (reference)

This file is **reference material** gathered during exploration. The authoritative contract is in `DATABASE_CONTRACT.md`.

## What we observed

### `ProductTestParameters`

- Structure behaves like a key-value table:
  - `(PartID, SequenceID, ParameterName) -> ParameterValue`
- Common patterns:
  - `SequenceID = 399` appears to be used by many **170XX** parts (QAL17 Final Test pattern)
  - `SequenceID = 300/600/650` appears in SPS examples (QAL15/16 family)

### Band definitions (PTP windows)

- Increasing band: `IncreasingLowerLimit` to `IncreasingUpperLimit`
- Decreasing band: `DecreasingLowerLimit` to `DecreasingUpperLimit`
- Reset band: `ResetBandLowerLimit` to `ResetBandUpperLimit`

### UOM mapping (Alicat codes in PTP)

`UnitsOfMeasure` numeric code matches Alicat’s internal unit codes (subset):

- `10` PSI
- `12` mTorr
- `13` Torr
- `15` inHg
- `19` cmH₂O
- `21` inH₂O

### `OrderCalibrationDetail`

Observed fields:

- `IncreasingActivation`, `DecreasingDeactivation`
- `IncreasingGap`, `DecreasingGap` (meaning unclear)
- `InSpec` (bit)
- `UnitsOfMeasure` appears to be a **string** (e.g., `PSIG`, `TORR`, `INHG`)

### Sequence formatting nuance

We observed patterns consistent with fixed-width storage:

- PTP `SequenceID` may contain padding (e.g., `300 `) and should be `.strip()`ed.
- `OrderCalibrationDetail.SequenceID` may be stored zero-padded (e.g., `0300`, `0600`, `0399`).

