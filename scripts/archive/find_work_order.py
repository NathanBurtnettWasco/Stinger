"""
Query recent work orders that have matching PTP parameters.

Usage (from repo root):
    python scripts/find_work_order.py
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
    config = load_config()
    db_config = config.get("database", {})

    if not initialize_database(db_config):
        raise SystemExit("Database init failed.")

    engine = get_engine()
    if engine is None:
        raise SystemExit("Database engine unavailable.")

    query = text(
        "SELECT TOP 10 "
        "m.ShopOrder, "
        "m.PartID, "
        "m.LastSequenceCalibrated, "
        "MAX(m.StartTime) AS LastStart "
        "FROM OrderCalibrationMaster m "
        "JOIN ProductTestParameters p "
        "  ON p.PartID = m.PartID "
        " AND LTRIM(RTRIM(p.SequenceID)) = LTRIM(RTRIM(m.LastSequenceCalibrated)) "
        "GROUP BY m.ShopOrder, m.PartID, m.LastSequenceCalibrated "
        "ORDER BY MAX(m.StartTime) DESC"
    )

    with engine.connect() as conn:
        rows = conn.execute(query).fetchall()

    if not rows:
        print("No matching work orders found.")
        return

    for row in rows:
        print(row)


if __name__ == "__main__":
    main()
