"""
Query PTP parameters for a given work order.

Usage:
    python scripts/ptp_query.py 51017150
"""
from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import text

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import load_config
from app.database.session import get_engine, initialize_database


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python scripts/ptp_query.py <shop_order>")

    shop_order = sys.argv[1].strip()
    if not shop_order:
        raise SystemExit("Shop order is required.")

    config = load_config()
    db_config = config.get("database", {})
    if not initialize_database(db_config):
        raise SystemExit("Database init failed.")

    engine = get_engine()
    if engine is None:
        raise SystemExit("Database engine unavailable.")

    with engine.connect() as conn:
        wo_row = conn.execute(
            text(
                "SELECT PartID, LastSequenceCalibrated "
                "FROM OrderCalibrationMaster "
                "WHERE ShopOrder = :shop"
            ),
            {"shop": shop_order},
        ).fetchone()

        print("Work Order:", shop_order, "->", wo_row)
        if not wo_row:
            return

        part_id = wo_row[0].strip() if wo_row[0] else ""
        sequence_id = wo_row[1].strip() if wo_row[1] else ""

        rows = conn.execute(
            text(
                "SELECT ParameterName, ParameterValue "
                "FROM ProductTestParameters "
                "WHERE PartID = :part "
                "AND LTRIM(RTRIM(SequenceID)) = LTRIM(RTRIM(:seq)) "
                "ORDER BY ParameterName"
            ),
            {"part": part_id, "seq": sequence_id},
        ).fetchall()

        print("PTP rows:", len(rows))
        for name, value in rows:
            name_text = name.strip() if name else name
            value_text = value.strip() if value else value
            print(f"{name_text}={value_text}")


if __name__ == "__main__":
    main()
