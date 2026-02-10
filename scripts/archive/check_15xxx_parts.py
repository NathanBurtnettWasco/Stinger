#!/usr/bin/env python
"""Check available sequences for 15018 part."""
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
    
    with engine.connect() as conn:
        # Check sequences for 15018
        result = conn.execute(text("""
            SELECT DISTINCT
                LTRIM(RTRIM(SequenceID)) AS SequenceID,
                ParameterName,
                LTRIM(RTRIM(ParameterValue)) AS Value
            FROM ProductTestParameters
            WHERE PartID = '15018'
            AND ParameterName IN ('ActivationTarget', 'TargetActivationDirection', 'UnitsOfMeasure', 'PressureReference')
            ORDER BY SequenceID, ParameterName
        """))
        
        print("\n15018 sequences:\n")
        rows = result.fetchall()
        for row in rows:
            print(f"  Seq {str(row[0]):<6} | {str(row[1]):<25} = {str(row[2])}")
        
        # Also check 16058 and 17000 series
        print("\n" + "="*70)
        result = conn.execute(text("""
            SELECT 
                ptp.PartID,
                LTRIM(RTRIM(ptp.SequenceID)) AS SequenceID,
                LTRIM(RTRIM(ptp.ParameterValue)) AS ActivationTarget,
                LTRIM(RTRIM(dir.ParameterValue)) AS Direction,
                LTRIM(RTRIM(ref.ParameterValue)) AS Ref
            FROM ProductTestParameters ptp
            JOIN ProductTestParameters dir ON ptp.PartID = dir.PartID 
                AND LTRIM(RTRIM(ptp.SequenceID)) = LTRIM(RTRIM(dir.SequenceID))
                AND dir.ParameterName = 'TargetActivationDirection'
            LEFT JOIN ProductTestParameters ref ON ptp.PartID = ref.PartID 
                AND LTRIM(RTRIM(ptp.SequenceID)) = LTRIM(RTRIM(ref.SequenceID))
                AND ref.ParameterName = 'PressureReference'
            WHERE ptp.ParameterName = 'ActivationTarget'
            AND ptp.PartID LIKE '15%' OR ptp.PartID LIKE '16%' OR ptp.PartID LIKE '17%' OR ptp.PartID LIKE '18%'
            AND LTRIM(RTRIM(dir.ParameterValue)) = 'Increasing'
            AND TRY_CAST(LTRIM(RTRIM(ptp.ParameterValue)) AS FLOAT) BETWEEN 8.0 AND 12.0
            ORDER BY ptp.PartID, SequenceID
        """))
        
        print("\nAll 15xxx-18xxx parts with ~9-10 PSI target:\n")
        rows = result.fetchall()
        print(f"{'PartID':<15} {'Seq':<6} {'Target':>8} {'Direction':<12} {'Ref':<10}")
        print("-" * 60)
        for row in rows:
            print(f"{str(row[0]).strip():<15} {str(row[1]).strip():<6} {str(row[2]).strip():>8} {str(row[3]).strip():<12} {str(row[4]).strip() if row[4] else '':<10}")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
