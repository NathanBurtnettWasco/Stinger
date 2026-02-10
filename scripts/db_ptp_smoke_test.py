"""
DB/PTP smoke test helper.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import load_config
from app.database.session import initialize_database
from app.database.operations import validate_shop_order
from app.services.ptp_service import load_ptp_from_db, load_ptp_from_dump, derive_test_setup


def _print_section(title: str, payload: Any) -> None:
    print(f"\n=== {title} ===")
    print(json.dumps(payload, indent=2, default=str))


def _resolve_part_sequence(
    shop_order: Optional[str], part_id: Optional[str], sequence_id: Optional[str]
) -> tuple[Optional[str], Optional[str], Optional[Dict[str, Any]]]:
    if not shop_order:
        return part_id, sequence_id, None

    details = validate_shop_order(shop_order)
    if not details:
        return None, None, None

    resolved_part = details.get("PartID")
    resolved_sequence = details.get("SequenceID")
    return str(resolved_part).strip(), str(resolved_sequence).strip(), details


def main() -> int:
    parser = argparse.ArgumentParser(description="Stinger DB/PTP smoke test.")
    parser.add_argument("--shop-order", help="Shop order to validate")
    parser.add_argument("--part-id", help="Part ID for PTP lookup")
    parser.add_argument("--sequence-id", help="Sequence ID for PTP lookup")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    config = load_config()
    db_ok = initialize_database(config.get("database", {}))

    part_id, sequence_id, details = _resolve_part_sequence(
        args.shop_order, args.part_id, args.sequence_id
    )

    if args.shop_order:
        _print_section("Work Order Details", details or {"error": "Shop order not found"})

    if not part_id or not sequence_id:
        print("\nNo PartID/SequenceID resolved. Provide --part-id/--sequence-id or --shop-order.")
        return 1

    ptp_params = load_ptp_from_db(part_id, sequence_id) if db_ok else {}
    source = "database" if ptp_params else "dump"
    if not ptp_params:
        ptp_params = load_ptp_from_dump(part_id, sequence_id)

    _print_section("PTP Source", {"source": source, "count": len(ptp_params)})
    _print_section("PTP Parameters (raw)", ptp_params)

    if ptp_params:
        setup = derive_test_setup(part_id, sequence_id, ptp_params)
        _print_section("Derived Test Setup", setup.__dict__)
        return 0

    print("\nNo PTP parameters found in DB or dumps.")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
