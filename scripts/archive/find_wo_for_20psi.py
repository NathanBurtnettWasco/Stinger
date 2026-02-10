#!/usr/bin/env python
"""Find shop orders for port A parts with ~20 PSI."""
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
    
    # Parts we found with ~20 PSI
    target_parts = [
        ('SBA01879-03', '400'),
        ('SBA01879-03', '225'),
        ('15031', '399'),
        ('17040', '399'),
    ]
    
    with engine.connect() as conn:
        print("Searching for shop orders with ~20 PSI parts...\n")
        
        for part_id, seq in target_parts:
            result = conn.execute(text("""
                SELECT TOP 5 ShopOrder, OrderQTY, OperatorID, LastSequenceCalibrated
                FROM OrderCalibrationMaster
                WHERE PartID = :part
                ORDER BY ShopOrder DESC
            """), {"part": part_id})
            
            rows = result.fetchall()
            if rows:
                print(f"\n{part_id} (Seq {seq}) - Shop Orders:")
                print(f"{'ShopOrder':<15} {'Qty':<6} {'Operator':<10} {'LastSeq':<8}")
                print("-" * 45)
                for row in rows:
                    print(f"{str(row[0]).strip():<15} {row[1]:<6} {str(row[2]).strip():<10} {str(row[3]).strip():<8}")
            else:
                print(f"\n{part_id} (Seq {seq}) - No shop orders found")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
