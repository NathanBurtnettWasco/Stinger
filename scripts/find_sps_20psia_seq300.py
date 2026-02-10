#!/usr/bin/env python
"""Find SPS parts with sequence 300 that activate at ~20 PSIA."""
import sys
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import load_config
from app.database.session import get_engine, initialize_database
from app.database.operations import load_test_parameters
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
        # Find SPS parts with sequence 300 and ~20 PSIA activation
        result = conn.execute(text("""
            SELECT DISTINCT
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
              AND ptp_target.PartID LIKE 'SPS%'
              AND LTRIM(RTRIM(ptp_target.SequenceID)) = '300'
              AND LTRIM(RTRIM(ptp_units.ParameterValue)) = '1'  -- PSI
              AND LTRIM(RTRIM(ISNULL(ptp_ref.ParameterValue, ''))) = 'Absolute'
              AND TRY_CAST(LTRIM(RTRIM(ptp_target.ParameterValue)) AS FLOAT) BETWEEN 18.0 AND 25.0
            ORDER BY TargetValue
        """))
        
        rows = result.fetchall()
        print(f"\nFound {len(rows)} SPS parts with sequence 300 and ~20 PSIA activation:\n")
        print(f"{'PartID':<25} {'Seq':<6} {'Target':>8} {'Direction':<12} {'Units':<6} {'Ref':<10}")
        print("-" * 80)
        for row in rows:
            print(f"{str(row[0]).strip():<25} {str(row[1]).strip():<6} {str(row[2]).strip():>8} {str(row[3]).strip():<12} {str(row[4]).strip():<6} {str(row[5]).strip():<10}")
        
        if rows:
            # Load full PTP for the first match (or all if user wants)
            print("\n" + "="*80)
            print("Full PTP Parameters:")
            print("="*80)
            
            for row in rows:
                part_id = str(row[0]).strip()
                seq_id = str(row[1]).strip()
                target = str(row[2]).strip()
                
                print(f"\n{'='*80}")
                print(f"PartID: {part_id}, Sequence: {seq_id}, Activation Target: {target} PSIA")
                print(f"{'='*80}")
                
                ptp_params = load_test_parameters(part_id, seq_id)
                if ptp_params:
                    # Sort parameters for readability
                    key_order = [
                        "ActivationTarget",
                        "TargetActivationDirection",
                        "PressureReference",
                        "UnitsOfMeasure",
                        "IncreasingLowerLimit",
                        "IncreasingUpperLimit",
                        "DecreasingLowerLimit",
                        "DecreasingUpperLimit",
                        "ResetBandLowerLimit",
                        "ResetBandUpperLimit",
                        "CommonTerminal",
                        "NormallyOpenTerminal",
                        "NormallyClosedTerminal",
                    ]
                    
                    # Print ordered keys first
                    for key in key_order:
                        if key in ptp_params:
                            value = ptp_params[key]
                            print(f"  {key:<30} = {value}")
                    
                    # Print any remaining parameters
                    remaining = set(ptp_params.keys()) - set(key_order)
                    if remaining:
                        print("\n  Other parameters:")
                        for key in sorted(remaining):
                            value = ptp_params[key]
                            print(f"  {key:<30} = {value}")
                else:
                    print("  No PTP parameters found")
            
            # Also output as JSON for easy copy-paste
            print("\n" + "="*80)
            print("PTP as JSON (for first match):")
            print("="*80)
            if rows:
                part_id = str(rows[0][0]).strip()
                seq_id = str(rows[0][1]).strip()
                ptp_params = load_test_parameters(part_id, seq_id)
                if ptp_params:
                    print(json.dumps(ptp_params, indent=2))
        else:
            print("\nNo matching SPS parts found with Absolute reference.")
            print("\nTrying broader search (any pressure reference)...")
            
            # Try without absolute filter
            result2 = conn.execute(text("""
                SELECT DISTINCT
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
                  AND ptp_target.PartID LIKE 'SPS%'
                  AND LTRIM(RTRIM(ptp_target.SequenceID)) = '300'
                  AND LTRIM(RTRIM(ptp_units.ParameterValue)) = '1'  -- PSI
                  AND TRY_CAST(LTRIM(RTRIM(ptp_target.ParameterValue)) AS FLOAT) BETWEEN 18.0 AND 25.0
                ORDER BY TargetValue
            """))
            
            rows2 = result2.fetchall()
            # Also check for absolute parts that would be ~20 PSIA (around 5-6 PSIG)
            result3 = conn.execute(text("""
                SELECT DISTINCT
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
                  AND ptp_target.PartID LIKE 'SPS%'
                  AND LTRIM(RTRIM(ptp_target.SequenceID)) = '300'
                  AND LTRIM(RTRIM(ptp_units.ParameterValue)) = '1'  -- PSI
                  AND LTRIM(RTRIM(ISNULL(ptp_ref.ParameterValue, ''))) = 'Absolute'
                  AND TRY_CAST(LTRIM(RTRIM(ptp_target.ParameterValue)) AS FLOAT) BETWEEN 18.0 AND 25.0
                ORDER BY TargetValue
            """))
            
            rows3 = result3.fetchall()
            if rows3:
                print(f"\nFound {len(rows3)} SPS parts with sequence 300 and ~20 PSIA (Absolute reference):\n")
                print(f"{'PartID':<25} {'Seq':<6} {'Target':>8} {'Direction':<12} {'Units':<6} {'Ref':<10}")
                print("-" * 80)
                for row in rows3:
                    print(f"{str(row[0]).strip():<25} {str(row[1]).strip():<6} {str(row[2]).strip():>8} {str(row[3]).strip():<12} {str(row[4]).strip():<6} {str(row[5]).strip():<10}")
                
                # Load full PTP for absolute matches
                print("\n" + "="*80)
                print("Full PTP Parameters (Absolute Reference):")
                print("="*80)
                
                for row in rows3:
                    part_id = str(row[0]).strip()
                    seq_id = str(row[1]).strip()
                    target = str(row[2]).strip()
                    
                    print(f"\n{'='*80}")
                    print(f"PartID: {part_id}, Sequence: {seq_id}, Activation Target: {target} PSIA")
                    print(f"{'='*80}")
                    
                    ptp_params = load_test_parameters(part_id, seq_id)
                    if ptp_params:
                        key_order = [
                            "ActivationTarget",
                            "TargetActivationDirection",
                            "PressureReference",
                            "UnitsOfMeasure",
                            "IncreasingLowerLimit",
                            "IncreasingUpperLimit",
                            "DecreasingLowerLimit",
                            "DecreasingUpperLimit",
                            "ResetBandLowerLimit",
                            "ResetBandUpperLimit",
                            "CommonTerminal",
                            "NormallyOpenTerminal",
                            "NormallyClosedTerminal",
                        ]
                        
                        for key in key_order:
                            if key in ptp_params:
                                value = ptp_params[key]
                                print(f"  {key:<30} = {value}")
                        
                        remaining = set(ptp_params.keys()) - set(key_order)
                        if remaining:
                            print("\n  Other parameters:")
                            for key in sorted(remaining):
                                value = ptp_params[key]
                                print(f"  {key:<30} = {value}")
                
                # JSON output for absolute matches
                print("\n" + "="*80)
                print("PTP as JSON (for first Absolute match):")
                print("="*80)
                if rows3:
                    part_id = str(rows3[0][0]).strip()
                    seq_id = str(rows3[0][1]).strip()
                    ptp_params = load_test_parameters(part_id, seq_id)
                    if ptp_params:
                        print(json.dumps(ptp_params, indent=2))
            
            if rows2:
                print(f"\nFound {len(rows2)} SPS parts with sequence 300 and ~20 PSI (Gauge reference):\n")
                print(f"{'PartID':<25} {'Seq':<6} {'Target':>8} {'Direction':<12} {'Units':<6} {'Ref':<10}")
                print("-" * 80)
                for row in rows2:
                    print(f"{str(row[0]).strip():<25} {str(row[1]).strip():<6} {str(row[2]).strip():>8} {str(row[3]).strip():<12} {str(row[4]).strip():<6} {str(row[5]).strip():<10}")
                
                # Load full PTP for these matches
                print("\n" + "="*80)
                print("Full PTP Parameters:")
                print("="*80)
                
                for row in rows2:
                    part_id = str(row[0]).strip()
                    seq_id = str(row[1]).strip()
                    target = str(row[2]).strip()
                    ref = str(row[5]).strip()
                    
                    print(f"\n{'='*80}")
                    print(f"PartID: {part_id}, Sequence: {seq_id}, Activation Target: {target} PSI ({ref})")
                    print(f"{'='*80}")
                    
                    ptp_params = load_test_parameters(part_id, seq_id)
                    if ptp_params:
                        # Sort parameters for readability
                        key_order = [
                            "ActivationTarget",
                            "TargetActivationDirection",
                            "PressureReference",
                            "UnitsOfMeasure",
                            "IncreasingLowerLimit",
                            "IncreasingUpperLimit",
                            "DecreasingLowerLimit",
                            "DecreasingUpperLimit",
                            "ResetBandLowerLimit",
                            "ResetBandUpperLimit",
                            "CommonTerminal",
                            "NormallyOpenTerminal",
                            "NormallyClosedTerminal",
                        ]
                        
                        # Print ordered keys first
                        for key in key_order:
                            if key in ptp_params:
                                value = ptp_params[key]
                                print(f"  {key:<30} = {value}")
                        
                        # Print any remaining parameters
                        remaining = set(ptp_params.keys()) - set(key_order)
                        if remaining:
                            print("\n  Other parameters:")
                            for key in sorted(remaining):
                                value = ptp_params[key]
                                print(f"  {key:<30} = {value}")
                    else:
                        print("  No PTP parameters found")
                
                # Also output as JSON for easy copy-paste
                print("\n" + "="*80)
                print("PTP as JSON (for first match):")
                print("="*80)
                if rows2:
                    part_id = str(rows2[0][0]).strip()
                    seq_id = str(rows2[0][1]).strip()
                    ptp_params = load_test_parameters(part_id, seq_id)
                    if ptp_params:
                        print(json.dumps(ptp_params, indent=2))
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
