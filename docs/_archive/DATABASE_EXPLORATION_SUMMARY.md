# Database Exploration Summary

This document captures findings from exploring the SQL Server database for Stinger test parameters and results.

## ProductTestParameters Structure

- **Table type**: Key-value table (PartID, SequenceID, ParameterName, ParameterValue)
- **Common sequences**: 
  - `399`: Appears to be QAL 17 Final Test
  - `600`: Often has TimeClean/TimeDry/TimeH2OPulse/TimeN2Pulse/TimePostPurge params
  - `300`, `625`, `650`: Other sequences seen for SPS01414-03

## Part Numbers Explored

- **17029**: Has PTP with SequenceID=399, Decreasing direction, UOM=1 (Unknown)
- **17036**: Has PTP with SequenceID=399, Decreasing direction, UOM=21 (inH2O)
- **17025**: Has PTP with SequenceID=399, Decreasing direction, UOM=21 (inH2O)
- **17088**: Has PTP with SequenceID=399, Increasing direction, UOM=21 (inH2O)
- **17030**: No PTP entries found (as expected per user)

Found 77 part numbers containing "170" in PTP.

## Band Definitions (ANSWERED)

- **Increasing band**: `IncreasingLowerLimit` to `IncreasingUpperLimit` — acceptable range for activation when pressure is increasing (may use `-Inf` for lower bound)
- **Decreasing band**: `DecreasingLowerLimit` to `DecreasingUpperLimit` — acceptable range for deactivation when pressure is decreasing (may use `Inf` for upper bound)
- **Reset band**: `ResetBandLowerLimit` to `ResetBandUpperLimit` — acceptable range for reset behavior (often `-Inf` to `Inf`)

### Examples from Data

- **17029**: Decreasing direction
  - Increasing: [-Inf, 11.0]
  - Decreasing: [7.8, 8.8]
  
- **17036**: Decreasing direction
  - Increasing: [-Inf, 75.0]
  - Decreasing: [40.0, 60.0]
  
- **17088**: Increasing direction
  - Increasing: [13.0, 18.0]
  - Decreasing: [5.0, Inf]

## Units of Measure (UOM) Mapping (ANSWERED)

`ProductTestParameters.UnitsOfMeasure` stores numeric codes matching Alicat's internal UOM codes:

- `0`: Default
- `1`: Unknown
- `2`: Pa
- `3`: hPa
- `6`: mbar
- `10`: PSI
- `11`: PSF
- `12`: mTorr
- `13`: Torr
- `14`: mmHg
- `15`: inHg
- `16`: mmH2O
- `19`: cmH2O
- `21`: inH2O
- `22`: atm

**Note**: `OrderCalibrationDetail.UnitsOfMeasure` stores strings (e.g., `PSIG`, `TORR`, `INHG`) rather than numeric codes.

### UOM Distribution in PTP

- Code `PSI`: 787 occurrences
- Code `19` (cmH2O): 648 occurrences
- Code `21` (inH2O): 336 occurrences
- Code `1` (Unknown): 209 occurrences

## OrderCalibrationMaster

- Does NOT have a `UnitsOfMeasure` column
- Fields include: ShopOrder, PartID, CalibrationDate, ActivationTarget, ActivationMinAllowable, ActivationMaxAllowable, OrderQTY

## OrderCalibrationDetail

- Stores both increasing and decreasing measurements regardless of `TargetActivationDirection`
- Fields include:
  - `IncreasingActivation`: Measured activation pressure (increasing direction)
  - `DecreasingDeactivation`: Measured deactivation pressure (decreasing direction)
  - `IncreasingGap`: Often 0.000 — meaning unclear
  - `DecreasingGap`: Often 0.000 — meaning unclear
  - `InSpec`: Bit flag for pass/fail
  - `UnitsOfMeasure`: String value (e.g., `PSIG`, `TORR`, `INHG`)

### UOM Distribution in OrderCalibrationDetail

- `INHG`: 473,303 occurrences
- `PSIG`: 433,314 occurrences
- `TORR`: 159,996 occurrences
- `mmHg @ 0° C`: 62,428 occurrences
- `PSI`: 42,693 occurrences

## Activation Directions

Both `Increasing` and `Decreasing` activation directions exist in the data:
- Decreasing: Switch activates as pressure decreases
- Increasing: Switch activates as pressure increases

## Questions Remaining

- What do the "Gap" fields (`IncreasingGap`, `DecreasingGap`) represent?
- How do we convert from PTP UOM codes to the string format used in `OrderCalibrationDetail`?
- How do we determine which `PartID` to query for PTP when a work order references a top-level assembly like `17030`?
