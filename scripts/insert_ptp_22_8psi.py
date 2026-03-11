#!/usr/bin/env python
"""Insert 22.8 psi PTP for PartID SPS00000 / Sequence 300.

Custom work order 'stinger228' is configured in stinger_config.yaml (custom_work_orders)
and resolves during login without a DB row. Run this script to ensure PTP exists.
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import load_config
from app.database.session import initialize_database
from app.database.operations import insert_test_parameters, load_test_parameters, validate_shop_order

# PTP for 22.8 psi activation (Gauge, Increasing), based on SPS01656-03 pattern
PTP_22_8_PSI = {
    "ActivationTarget": "22.800000",
    "TargetActivationDirection": "Increasing",
    "PressureReference": "Gauge",
    "UnitsOfMeasure": "1",
    "IncreasingLowerLimit": "22.550000",
    "IncreasingUpperLimit": "23.050000",
    "DecreasingLowerLimit": "10.000000",
    "DecreasingUpperLimit": "Inf",
    "ResetBandLowerLimit": "-Inf",
    "ResetBandUpperLimit": "Inf",
    "CommonTerminal": "4",
    "NormallyOpenTerminal": "1",
    "NormallyClosedTerminal": "3",
    # Legacy fields for DB consistency with other SPS parts
    "ControlPressure1": "0.000000",
    "ControlPressure2": "5.000000",
    "ControlPressure3": "22.800000",
    "ControlPressure4": "30.000000",
    "ControlPressure5": "50.000000",
    "RateTarget1": "0.500000",
    "RateTarget2": "1.000000",
    "RateTarget3": "5.000000",
}


def main() -> int:
    config = load_config()
    db_config = config.get("database", {})
    if not initialize_database(db_config):
        print("ERROR: Database init failed")
        return 1

    part_id = "SPS00000"
    sequence_id = "300"
    shop_order = "stinger228"

    if not insert_test_parameters(part_id, sequence_id, PTP_22_8_PSI):
        print("ERROR: Failed to insert PTP")
        return 1

    print(f"Successfully inserted PTP for {part_id} / {sequence_id}")

    # Verify PTP
    loaded = load_test_parameters(part_id, sequence_id)
    if loaded:
        print(f"Verified PTP: loaded {len(loaded)} parameters")
        print(f"  ActivationTarget = {loaded.get('ActivationTarget', '?')}")
    else:
        print("Warning: Could not verify PTP - load returned empty")

    # Verify custom work order (from stinger_config.yaml)
    wo = validate_shop_order(shop_order)
    if wo:
        print(f"Custom work order '{shop_order}': PartID={wo.get('PartID')}, Sequence={wo.get('SequenceID')}")
    else:
        print(f"Warning: Custom work order '{shop_order}' not found in config.")

    print(f"\nTo use: enter Shop Order '{shop_order}' during login to load 22.8 psi PTP.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
