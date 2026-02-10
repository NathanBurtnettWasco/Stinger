#!/usr/bin/env python
"""Find parts with ~23 PSIA absolute (or ~9-10 PSIG) activation target."""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import load_config
from app.database.session import get_engine, initialize_database
from sqlalchemy import text

def main():
    config = load_config()
    db_config = config.get("database", {})
    if not initialize_database(db_config):
        print("ERROR: Database init failed")
        return 1
    
    engine = get_engine()
    if engine is None:
        print("ERROR: Could not connect to database")
        return 1
    
    # Baro ~13.6, so 23 PSIA = ~9.4 PSIG
    # Look for parts with 8-12 PSI gauge target (Increasing)
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT 
                ptp_target.PartID,
                LTRIM(RTRIM(ptp_target.SequenceID)) AS SequenceID,
                LTRIM(RTRIM(ptp_target.ParameterValue)) AS ActivationTarget,
                LTRIM(RTRIM(ptp_dir.ParameterValue)) AS Direction,
                LTRIM(RTRIM(ptp_units.ParameterValue)) AS UnitsCode,
                LTRIM(RTRIM(ISNULL(ptp_ref.ParameterValue, ''))) AS PressureReference,
                TRY_CAST(LTRIM(RTRIM(ptp_target.ParameterValue)) AS FLOAT) AS TargetValue
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
              AND LTRIM(RTRIM(ptp_units.ParameterValue)) = '1'  -- PSI
              AND TRY_CAST(LTRIM(RTRIM(ptp_target.ParameterValue)) AS FLOAT) BETWEEN 8.0 AND 12.0
            ORDER BY TargetValue
        """))
        
        rows = result.fetchall()
        print(f"\nParts with ~9-10 PSIG target (~22-24 PSIA with 13.6 baro):\n")
        print(f"{'PartID':<20} {'Seq':<6} {'Target':>8} {'Direction':<12} {'Units':<6} {'Ref':<10}")
        print("-" * 70)
        for row in rows:
            print(f"{str(row[0]).strip():<20} {str(row[1]).strip():<6} {str(row[2]).strip():>8} {str(row[3]).strip():<12} {str(row[4]).strip():<6} {str(row[5]).strip():<10}")
        
        if rows:
            print(f"\n>>> Recommendation for ~23 PSIA:")
            print(f"    Part: {rows[0][0].strip()}")
            print(f"    Sequence: {rows[0][1].strip()}")
            print(f"    Target: {rows[0][2].strip()} PSIG ({float(rows[0][6]) + 13.6:.1f} PSIA approx)")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
