# Stinger Database Description (factual)

This document describes the data Stinger needs to load/store. It avoids speculative tables/DDL until confirmed against the real database.

## Data sources

### Work order context

The UI shows (at minimum):

- operator ID (manual entry)
- shop order (manual entry)
- sequence (auto-filled from `OrderCalibrationMaster`)
- part ID (auto-filled from `OrderCalibrationMaster`)
- quantity / progress (X / Y done) (auto-filled from `OrderCalibrationMaster`, not strictly required but ideal)

**Auto-fill behavior**: When operator enters Shop Order, system queries `OrderCalibrationMaster` table to auto-fill Part ID, Sequence ID (`LastSequenceCalibrated`), and Quantity (`OrderQTY`). Similar to Functional Stand's pattern but using `OrderCalibrationMaster` instead of `DPI_GeneralMaster`.

Stinger loads this context at the system level (shared across ports).

### Test parameters (“PTP”)

Stinger loads test parameters per part/sequence (commonly from a `ProductTestParameters`-style table).

Parameters must support:

- pressure targets / ranges for the test
- ramp behavior (fast vs slow behavior, if applicable)
- acceptance ranges for activation and deactivation
- circuit semantics if needed (NO/NC, increasing/decreasing logic)

#### Confirmed: `ProductTestParameters`

For Scorpion part `SPS01414-03`, querying `ProductTestParameters` shows sequences with parameter families such as:

- **Activation target + control limits**: `ActivationTarget`, `ActivationLowerControlLimit`, `ActivationUpperControlLimit`
- **Direction semantics**: `TargetActivationDirection` (e.g. `Increasing`)
- **Acceptance windows**:
  - `IncreasingLowerLimit` / `IncreasingUpperLimit`
  - `DecreasingLowerLimit` / `DecreasingUpperLimit`
  - `ResetBandLowerLimit` / `ResetBandUpperLimit`
- **Control/ramp shaping**:
  - `ControlPressure1..N`
  - `RateTarget1..N`
- **Electrical terminal mapping**: `CommonTerminal`, `NormallyOpenTerminal`, `NormallyClosedTerminal`
- **Pressure reference selection**: `PressureReference` (e.g. `Gauge`)
- **Units encoding**: `UnitsOfMeasure` (numeric codes matching Alicat's internal UOM codes; see Units of Measure section below)

Sequence IDs observed in PTP for `SPS01414-03` include: `300`, `600`, `650` (and a smaller `625` family that looks like a cycle/pressure endurance config).

## Data we store (per tested unit, per port)

Each test result record must support:

- **identifiers**: serial number, port ID, shop order, part ID, operator ID, equipment ID, timestamp
- **measured points**:
  - measured activation pressure (and timestamp if useful)
  - measured deactivation pressure (and timestamp if useful)
- **derived values**:
  - increasing band
  - decreasing band
  - reset band
- **evaluation**:
  - activation in range (bool)
  - deactivation in range (bool)
  - overall pass/fail (bool)
  - failure reason (string / enum)
- **context snapshots (optional but valuable)**:
  - the parameter set used (or a reference to it)
  - hardware identifiers (Alicat serial, DAQ device name)
  - software version

## Confirmed result storage tables

### `OrderCalibrationMaster`

The database contains a master record per work order with fields including:

- `ShopOrder`, `PartID`, `OperatorID`, `EquipmentID`
- `StartTime`, `FinishTime`, `CalibrationDate`
- `ActivationMinAllowable`, `ActivationMaxAllowable`
- `OrderQTY`

### `OrderCalibrationDetail`

The database contains per-unit/per-sequence detail rows with fields including:

- identifiers: `ShopOrder`, `SequenceID`, `PartID`, `SerialNumber`, `InspectionDate`, `OperatorID`, `EquipmentID`
- measured values:
  - `IncreasingActivation`
  - `DecreasingDeactivation`
  - `IncreasingGap`
  - `DecreasingGap`
  - optional: `MaxPressureAchieved`, `GageReferenceDiff`
- evaluation: `InSpec` (bit)
- units: `UnitsOfMeasure`

#### Note on sequence formatting

`OrderCalibrationDetail.SequenceID` is stored as `nchar` and often appears **zero-padded** (e.g., `0300`, `0600`, `0650`) even when `ProductTestParameters.SequenceID` is stored as `300`, `600`, `650`.

## Units of Measure

`ProductTestParameters.UnitsOfMeasure` stores numeric codes that correspond to Alicat's internal unit codes. The mapping is:

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

Note: `OrderCalibrationDetail.UnitsOfMeasure` stores string values (e.g., `PSIG`, `TORR`, `INHG`) rather than numeric codes.

## Band definitions

The acceptance ranges stored in PTP are:

- **Increasing band**: `IncreasingLowerLimit` to `IncreasingUpperLimit` — acceptable range for activation when pressure is increasing. May use `-Inf` for lower bound (no minimum).
- **Decreasing band**: `DecreasingLowerLimit` to `DecreasingUpperLimit` — acceptable range for deactivation when pressure is decreasing. May use `Inf` for upper bound (no maximum).
- **Reset band**: `ResetBandLowerLimit` to `ResetBandUpperLimit` — acceptable range for reset behavior. Often `-Inf` to `Inf` (no constraint).

The system evaluates whether the measured activation/deactivation pressures fall within these bands to determine pass/fail.

## Data we do NOT assume

Until you confirm, this doc does not assume:

- any additional Stinger-specific result tables beyond the confirmed `OrderCalibration*` tables
- whether results are stored as one row per unit or one row per "attempt"

Those are captured in `docs/90_OPEN_QUESTIONS.md`.

