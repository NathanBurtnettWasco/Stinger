"""
Pressure sweep + switch state logger.

Runs a controlled pressure sweep on one port and logs:
- Transducer pressure (LabJack)
- NO/NC switch state (LabJack)
- All DIO0-19 raw states
- Alicat pressure + setpoint

Usage:
    python scripts/switch_sweep_test.py --port port_a
"""

from __future__ import annotations

import argparse
import csv
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import load_config
from app.hardware import labjack as labjack_module
from app.hardware.alicat import AlicatController
from app.hardware.labjack import LabJackController

logger = logging.getLogger(__name__)


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _build_alicat_controller(config: Dict[str, Any], port_key: str) -> AlicatController:
    alicat_base = config.get("hardware", {}).get("alicat", {})
    port_cfg = alicat_base.get(port_key, {})
    alicat_config = {
        "com_port": port_cfg.get("com_port"),
        "address": port_cfg.get("address"),
        "baudrate": alicat_base.get("baudrate", 19200),
        "timeout_s": alicat_base.get("timeout_s", 0.05),
    }
    return AlicatController(alicat_config)


def _build_labjack_controller(config: Dict[str, Any], port_key: str) -> LabJackController:
    lj_cfg = config.get("hardware", {}).get("labjack", {})
    base_config = {
        "device_type": lj_cfg.get("device_type", "T7"),
        "connection_type": lj_cfg.get("connection_type", "USB"),
        "identifier": lj_cfg.get("identifier", "ANY"),
    }
    port_cfg = lj_cfg.get(port_key, {})
    return LabJackController({**base_config, **port_cfg})


def psig_to_psia(psig: float) -> float:
    """Convert gauge pressure to absolute (add atmospheric ~14.7 PSI)."""
    return psig + 14.7

def run_sweep(
    port_key: str,
    ramp_rate: float,
    target_high: float,
    target_low: float,
    hold_high: float,
    hold_low: float,
    sample_hz: float,
    no_dio: int | None,
    nc_dio: int | None,
) -> int:
    config = load_config()

    if not labjack_module.LJM_AVAILABLE:
        print("LabJack LJM not available.")
        return 1

    labjack = _build_labjack_controller(config, port_key)
    if not labjack.configure():
        print(f"LabJack config failed: {labjack._last_status}")
        return 1

    alicat = _build_alicat_controller(config, port_key)
    if not alicat.connect():
        print(f"Alicat connect failed: {alicat._last_status}")
        labjack.cleanup()
        return 1

    try:
        # Ensure Alicat is in closed-loop control mode (not hold)
        print("Canceling hold mode...")
        alicat.cancel_hold()
        
        # For pressure switches: solenoid to atmosphere (False)
        # For vacuum switches: solenoid to vacuum (True)
        print("Setting solenoid to atmosphere...")
        labjack.set_solenoid(to_vacuum=False)

        # Ramp rate in current Alicat units (assume PSI)
        print(f"Setting ramp rate to {ramp_rate} PSI/s...")
        alicat.set_ramp_rate(ramp_rate)

        # Prepare CSV log
        log_dir = PROJECT_ROOT / "logs"
        os.makedirs(log_dir, exist_ok=True)
        log_path = log_dir / f"switch_sweep_{port_key}_{_timestamp()}.csv"

        dio_indices = list(range(20))
        dio_names = [f"DIO{idx}" for idx in dio_indices]

        def read_dio() -> List[int]:
            handle = labjack._shared_handle
            if handle is None:
                return [0 for _ in dio_indices]
            values = labjack_module.ljm.eReadNames(handle, len(dio_names), dio_names)
            return [int(v) for v in values]

        start = time.monotonic()
        sample_interval = 1.0 / max(sample_hz, 1.0)

        with open(log_path, "w", newline="") as csv_file:
            writer = csv.writer(csv_file)
            header = [
                "timestamp_s",
                "elapsed_s",
                "transducer_psi",
                "alicat_pressure",
                "alicat_setpoint",
                "no_active",
                "nc_active",
                "no_raw",
                "nc_raw",
            ] + dio_names
            writer.writerow(header)

            def sample_row() -> None:
                now = time.monotonic()
                reading = labjack.read_transducer()
                switch = labjack.read_switch_state()
                alicat_reading = alicat.read_status()
                dio_states = read_dio()
                no_raw = None
                nc_raw = None
                if no_dio is not None and 0 <= no_dio < len(dio_states):
                    no_raw = dio_states[no_dio]
                if nc_dio is not None and 0 <= nc_dio < len(dio_states):
                    nc_raw = dio_states[nc_dio]
                writer.writerow(
                    [
                        time.time(),
                        now - start,
                        reading.pressure if reading else None,
                        alicat_reading.pressure if alicat_reading else None,
                        alicat_reading.setpoint if alicat_reading else None,
                        int(switch.no_active) if switch else None,
                        int(switch.nc_active) if switch else None,
                        no_raw,
                        nc_raw,
                    ]
                    + dio_states
                )

            def run_segment(target_setpoint_psig: float, duration: float) -> None:
                target_psia = psig_to_psia(target_setpoint_psig)
                print(f"Setting setpoint to {target_setpoint_psig} PSIG ({target_psia:.1f} PSIA)...")
                success = alicat.set_pressure(target_psia)
                print(f"Setpoint command {'succeeded' if success else 'failed'}")
                segment_start = time.monotonic()
                next_sample = segment_start
                while time.monotonic() - segment_start < duration:
                    now = time.monotonic()
                    if now >= next_sample:
                        sample_row()
                        next_sample = now + sample_interval
                    time.sleep(0.002)

            current = alicat.read_status()
            run_segment(current.setpoint if current else 0.0, 1.0)
            run_segment(target_high, hold_high)
            run_segment(target_low, hold_low)

        print(f"Log written: {log_path}")
        return 0
    finally:
        try:
            alicat.disconnect()
        except Exception:
            pass
        labjack.cleanup()


def main() -> int:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")

    parser = argparse.ArgumentParser(description="Sweep pressure and log switch states.")
    parser.add_argument("--port", default="port_a", choices=["port_a", "port_b"])
    parser.add_argument("--ramp", type=float, default=2.0, help="Ramp rate in PSI/s")
    parser.add_argument("--high", type=float, default=35.0, help="High setpoint (PSI)")
    parser.add_argument("--low", type=float, default=0.0, help="Low setpoint (PSI)")
    parser.add_argument("--hold-high", type=float, default=12.0, help="Hold high duration (s)")
    parser.add_argument("--hold-low", type=float, default=12.0, help="Hold low duration (s)")
    parser.add_argument("--hz", type=float, default=20.0, help="Sample rate (Hz)")
    parser.add_argument("--no-dio", type=int, default=None, help="Override NO DIO index")
    parser.add_argument("--nc-dio", type=int, default=None, help="Override NC DIO index")

    args = parser.parse_args()
    return run_sweep(
        port_key=args.port,
        ramp_rate=args.ramp,
        target_high=args.high,
        target_low=args.low,
        hold_high=args.hold_high,
        hold_low=args.hold_low,
        sample_hz=args.hz,
        no_dio=args.no_dio,
        nc_dio=args.nc_dio,
    )


if __name__ == "__main__":
    raise SystemExit(main())
