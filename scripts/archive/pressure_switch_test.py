"""
Pressure switch wiring test (DB9 NO/NC/COM).

Uses COM-low convention when switch_active_low is true in config:
  COM = output driven low. NO/NC = inputs (floating = high).
  When the switch connects COM to a terminal, that terminal goes low = connectivity.
  active = that path has connectivity (raw low when connected to COM).

Usage:
    # Preferred: consolidated hardware CLI
    python scripts/hardware.py switch --port port_a --com-dio 3

    # Backwards-compatible direct entry point
    python scripts/pressure_switch_test.py --port port_a --com-dio 3
    python scripts/pressure_switch_test.py --port port_b --com-dio 16 --samples 50 --interval 0.2
"""

from __future__ import annotations

import argparse
import csv
import logging
import sys
import time
from pathlib import Path
from typing import List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import get_port_config, load_config
from app.hardware.labjack import LabJackController

try:
    from labjack import ljm
except Exception:
    ljm = None


def _set_com_state(controller: LabJackController, com_dio: int, high: bool) -> bool:
    if not controller.hardware_available():
        return True
    if ljm is None:
        return False
    handle = controller._shared_handle
    if handle is None:
        return False
    try:
        ljm.eWriteName(handle, f"DIO{com_dio}", 1 if high else 0)
        return True
    except Exception:
        return False


def _read_samples(
    controller: LabJackController,
    samples: int,
    interval_s: float,
) -> List[dict]:
    rows = []
    for _ in range(samples):
        state = controller.read_switch_state()
        timestamp = time.time()
        if state is None:
            rows.append({
                "timestamp": timestamp,
                "no_active": None,
                "nc_active": None,
                "valid": None,
            })
        else:
            rows.append({
                "timestamp": timestamp,
                "no_active": state.no_active,
                "nc_active": state.nc_active,
                "valid": state.is_valid,
            })
        time.sleep(interval_s)
    return rows


def _summarize(rows: List[dict]) -> dict:
    total = len(rows)
    no_high = sum(1 for r in rows if r["no_active"] is True)
    nc_high = sum(1 for r in rows if r["nc_active"] is True)
    both_high = sum(1 for r in rows if r["no_active"] is True and r["nc_active"] is True)
    both_low = sum(1 for r in rows if r["no_active"] is False and r["nc_active"] is False)
    invalid = sum(1 for r in rows if r["valid"] is False)
    return {
        "total_samples": total,
        "no_high": no_high,
        "nc_high": nc_high,
        "both_high": both_high,
        "both_low": both_low,
        "invalid": invalid,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Pressure switch NO/NC/COM test")
    parser.add_argument(
        '--allow-legacy',
        action='store_true',
        help='Temporarily allow deprecated direct script execution.',
    )
    parser.add_argument("--port", choices=["port_a", "port_b"], default="port_a")
    parser.add_argument("--com-dio", type=int, required=True, help="DIO for COM pin (drive high)")
    parser.add_argument("--no-dio", type=int, default=None, help="Override NO DIO pin")
    parser.add_argument("--nc-dio", type=int, default=None, help="Override NC DIO pin")
    parser.add_argument("--samples", type=int, default=50, help="Samples per state")
    parser.add_argument("--interval", type=float, default=0.2, help="Seconds between samples")
    parser.add_argument("--output", type=str, default="", help="Optional CSV output path")
    args = parser.parse_args()

    if not args.allow_legacy:
        print('[ERROR] Direct script execution is deprecated.')
        print('Use: python scripts/hardware.py switch ...')
        print('If you must run this script directly, add --allow-legacy.')
        return 2

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    config = load_config()
    port_cfg = get_port_config(config, args.port)
    lj_cfg = {**config["hardware"]["labjack"], **port_cfg["labjack"]}

    no_dio = args.no_dio if args.no_dio is not None else lj_cfg.get("switch_no_dio")
    nc_dio = args.nc_dio if args.nc_dio is not None else lj_cfg.get("switch_nc_dio")
    com_dio = args.com_dio if args.com_dio is not None else lj_cfg.get("switch_com_dio")

    if no_dio is None or nc_dio is None:
        print("[FAIL] NO/NC DIO pins are not configured. Use --no-dio/--nc-dio.")
        return 1

    if com_dio is None:
        print("[FAIL] COM DIO pin is not configured. Use --com-dio.")
        return 1

    controller = LabJackController(lj_cfg)
    if not controller.configure():
        print(f"[FAIL] LabJack configuration failed: {controller._last_status}")
        return 1

    com_state = lj_cfg.get("switch_com_state", 0)
    controller.configure_di_pins(no_dio, nc_dio, com_dio, com_state=com_state)

    active_low = lj_cfg.get("switch_active_low", False)
    print("\n=== PRESSURE SWITCH TEST ===")
    print(f"Port: {args.port}")
    print(f"NO DIO: {no_dio} | NC DIO: {nc_dio} | COM DIO: {com_dio} (COM={'LOW' if com_state == 0 else 'HIGH'})")
    print(f"Active-low: {active_low} (active = path has connectivity to COM)")
    print(f"Samples: {args.samples} | Interval: {args.interval:.2f}s")

    output_path = Path(args.output) if args.output else None
    all_rows: List[dict] = []

    try:
        print("\n[STEP 1] COM LOW (0)")
        if not _set_com_state(controller, args.com_dio, high=False):
            print("[WARNING] Could not set COM low")
        dio_raw = controller.read_dio_values()
        if dio_raw is not None:
            c, no, nc = com_dio, no_dio, nc_dio
            print(f"  Raw DIO (COM={c}, NO={no}, NC={nc}): COM={dio_raw.get(c, '?')} NO={dio_raw.get(no, '?')} NC={dio_raw.get(nc, '?')}")
        rows = _read_samples(controller, args.samples, args.interval)
        all_rows.extend([{"phase": "com_low", **r} for r in rows])
        summary = _summarize(rows)
        print(f"  NO active: {summary['no_high']} | NC active: {summary['nc_high']} | both: {summary['both_high']} | neither: {summary['both_low']}")

        print("\n[STEP 2] COM HIGH (1)")
        if not _set_com_state(controller, args.com_dio, high=True):
            print("[WARNING] Could not set COM high")
        dio_raw = controller.read_dio_values()
        if dio_raw is not None:
            c, no, nc = com_dio, no_dio, nc_dio
            print(f"  Raw DIO (COM={c}, NO={no}, NC={nc}): COM={dio_raw.get(c, '?')} NO={dio_raw.get(no, '?')} NC={dio_raw.get(nc, '?')}")
        rows = _read_samples(controller, args.samples, args.interval)
        all_rows.extend([{"phase": "com_high", **r} for r in rows])
        summary = _summarize(rows)
        print(f"  NO active: {summary['no_high']} | NC active: {summary['nc_high']} | both: {summary['both_high']} | neither: {summary['both_low']}")

    finally:
        _set_com_state(controller, args.com_dio, high=False)
        controller.cleanup()

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["phase", "timestamp", "no_active", "nc_active", "valid"])
            for row in all_rows:
                writer.writerow([
                    row["phase"],
                    row["timestamp"],
                    row["no_active"],
                    row["nc_active"],
                    row["valid"],
                ])
        print(f"\nCSV saved: {output_path}")

    print("\nTest complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
