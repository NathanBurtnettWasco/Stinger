#!/usr/bin/env python
"""
Find PTP records that match the bench switch characteristics.

Port A: ~20-25 PSI, Increasing direction
Port B: Vacuum (Decreasing direction, below atmosphere)
"""
import sys
from pathlib import Path

# Ensure the project root is on sys.path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from app.database.session import get_engine


def main() -> None:
    engine = get_engine()
    if engine is None:
        print("ERROR: Could not connect to database.")
        sys.exit(1)

    with engine.connect() as conn:
        # --- Port A: ~20-25 PSI, Increasing ---
        print("=" * 80)
        print("PORT A candidates: ActivationTarget 18-27 PSI, Increasing")
        print("=" * 80)
        result = conn.exec_driver_sql(
            """
            SELECT DISTINCT
                ptp_target.PartID,
                LTRIM(RTRIM(ptp_target.SequenceID)) AS SequenceID,
                LTRIM(RTRIM(ptp_target.ParameterValue)) AS ActivationTarget,
                LTRIM(RTRIM(ptp_dir.ParameterValue)) AS Direction,
                LTRIM(RTRIM(ptp_units.ParameterValue)) AS UnitsCode,
                LTRIM(RTRIM(ISNULL(ptp_ref.ParameterValue, ''))) AS PressureReference
            FROM ProductTestParameters ptp_target
            JOIN ProductTestParameters ptp_dir
                ON ptp_target.PartID = ptp_dir.PartID
               AND LTRIM(RTRIM(ptp_target.SequenceID)) = LTRIM(RTRIM(ptp_dir.SequenceID))
               AND ptp_dir.ParameterName = 'TargetActivationDirection'
            JOIN ProductTestParameters ptp_units
                ON ptp_target.PartID = ptp_units.PartID
               AND LTRIM(RTRIM(ptp_target.SequenceID)) = LTRIM(RTRIM(ptp_units.SequenceID))
               AND ptp_units.ParameterName = 'UnitsOfMeasure'
            LEFT JOIN ProductTestParameters ptp_ref
                ON ptp_target.PartID = ptp_ref.PartID
               AND LTRIM(RTRIM(ptp_target.SequenceID)) = LTRIM(RTRIM(ptp_ref.SequenceID))
               AND ptp_ref.ParameterName = 'PressureReference'
            WHERE ptp_target.ParameterName = 'ActivationTarget'
              AND LTRIM(RTRIM(ptp_dir.ParameterValue)) = 'Increasing'
              AND LTRIM(RTRIM(ptp_units.ParameterValue)) = '1'
              AND TRY_CAST(LTRIM(RTRIM(ptp_target.ParameterValue)) AS FLOAT) BETWEEN 18.0 AND 27.0
            ORDER BY ptp_target.PartID, SequenceID
            """
        )
        rows = result.fetchall()
        if rows:
            print(f"{'PartID':<20} {'Seq':<6} {'Target':>8} {'Direction':<12} {'Units':<6} {'Ref':<10}")
            print("-" * 70)
            for row in rows:
                print(f"{str(row[0]).strip():<20} {str(row[1]).strip():<6} {str(row[2]).strip():>8} {str(row[3]).strip():<12} {str(row[4]).strip():<6} {str(row[5]).strip():<10}")
        else:
            print("  (no matches)")

        # --- Port B: Vacuum / Decreasing ---
        print()
        print("=" * 80)
        print("PORT B candidates: Decreasing direction, vacuum range")
        print("=" * 80)
        result = conn.exec_driver_sql(
            """
            SELECT DISTINCT
                ptp_target.PartID,
                LTRIM(RTRIM(ptp_target.SequenceID)) AS SequenceID,
                LTRIM(RTRIM(ptp_target.ParameterValue)) AS ActivationTarget,
                LTRIM(RTRIM(ptp_dir.ParameterValue)) AS Direction,
                LTRIM(RTRIM(ptp_units.ParameterValue)) AS UnitsCode,
                LTRIM(RTRIM(ISNULL(ptp_ref.ParameterValue, ''))) AS PressureReference
            FROM ProductTestParameters ptp_target
            JOIN ProductTestParameters ptp_dir
                ON ptp_target.PartID = ptp_dir.PartID
               AND LTRIM(RTRIM(ptp_target.SequenceID)) = LTRIM(RTRIM(ptp_dir.SequenceID))
               AND ptp_dir.ParameterName = 'TargetActivationDirection'
            JOIN ProductTestParameters ptp_units
                ON ptp_target.PartID = ptp_units.PartID
               AND LTRIM(RTRIM(ptp_target.SequenceID)) = LTRIM(RTRIM(ptp_units.SequenceID))
               AND ptp_units.ParameterName = 'UnitsOfMeasure'
            LEFT JOIN ProductTestParameters ptp_ref
                ON ptp_target.PartID = ptp_ref.PartID
               AND LTRIM(RTRIM(ptp_target.SequenceID)) = LTRIM(RTRIM(ptp_ref.SequenceID))
               AND ptp_ref.ParameterName = 'PressureReference'
            WHERE ptp_target.ParameterName = 'ActivationTarget'
              AND LTRIM(RTRIM(ptp_dir.ParameterValue)) = 'Decreasing'
              AND (
                  -- PSI absolute, target below atmosphere
                  (LTRIM(RTRIM(ptp_units.ParameterValue)) = '1'
                   AND TRY_CAST(LTRIM(RTRIM(ptp_target.ParameterValue)) AS FLOAT) < 14.7)
                  OR
                  -- Torr/mmHg (vacuum range)
                  (LTRIM(RTRIM(ptp_units.ParameterValue)) IN ('12','13','14','21')
                   AND TRY_CAST(LTRIM(RTRIM(ptp_target.ParameterValue)) AS FLOAT) < 760)
              )
            ORDER BY ptp_target.PartID, SequenceID
            """
        )
        rows = result.fetchall()
        if rows:
            print(f"{'PartID':<20} {'Seq':<6} {'Target':>8} {'Direction':<12} {'Units':<6} {'Ref':<10}")
            print("-" * 70)
            for row in rows:
                print(f"{str(row[0]).strip():<20} {str(row[1]).strip():<6} {str(row[2]).strip():>8} {str(row[3]).strip():<12} {str(row[4]).strip():<6} {str(row[5]).strip():<10}")
        else:
            print("  (no matches)")

    print("\nDone.")


if __name__ == "__main__":
    main()
