#!/usr/bin/env python3
"""Temporary script: sweep setpoints and log a tail of Alicat, Mensor, and transducer readings.

Run from project root so quality_cal and app are on the path:
  python scripts/sweep_readings_temp.py
  python scripts/sweep_readings_temp.py --points 10 15 20 25 --hold 15 --rate 2

Output is printed to stdout and optionally appended to a CSV for inspection.
"""

from __future__ import annotations

import argparse
import csv
import logging
import sys
import threading
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.hardware.port import PortManager
from quality_cal.config import load_config, parse_quality_settings, setup_logging
from quality_cal.core.hardware_helpers import (
    alicat_abs_psia,
    command_target_pressure,
    infer_barometric_psia,
    prepare_port_for_target,
    transducer_abs_psia,
    wait_until_near_target,
)
from quality_cal.core.mensor_reader import MensorReader

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sweep pressure setpoints and log Alicat / Mensor / transducer tail of readings."
    )
    parser.add_argument(
        "--points",
        type=float,
        nargs="+",
        default=[10.0, 15.0, 20.0, 25.0],
        help="Setpoints in psia to sweep (default: 10 15 20 25)",
    )
    parser.add_argument(
        "--hold",
        type=float,
        default=12.0,
        help="Seconds to hold at each setpoint while sampling (default: 12)",
    )
    parser.add_argument(
        "--rate",
        type=float,
        default=2.0,
        help="Sample rate Hz during hold (default: 2)",
    )
    parser.add_argument(
        "--port",
        choices=("port_a", "port_b"),
        default="port_a",
        help="Which port to use (default: port_a)",
    )
    parser.add_argument(
        "--csv",
        type=Path,
        default=None,
        help="Optional path to append CSV output (timestamp, target, alicat, mensor, transducer, mensor_raw)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Path to write all printed output (e.g. sweep_run_output.txt)",
    )
    args = parser.parse_args()

    if args.out is not None:
        out_path = args.out if args.out.is_absolute() else (PROJECT_ROOT / args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        args._out_file = open(out_path, "w", encoding="utf-8")
        args._out_path = out_path
        sys.stdout = args._out_file
        sys._sweep_out_file = args._out_file
    else:
        args._out_file = None
        args._out_path = None
        sys._sweep_out_file = None

    config = load_config()
    setup_logging(config)
    settings = parse_quality_settings(config)

    # Apply discovery so COM ports match current hardware
    from quality_cal.core.hardware_discovery import (
        discover_alicat_assignments,
        discover_mensor_port,
    )

    hw = config.setdefault("hardware", {})
    alicat_cfg = hw.setdefault("alicat", {})
    port_a_cfg = alicat_cfg.setdefault("port_a", {})
    port_b_cfg = alicat_cfg.setdefault("port_b", {})
    mensor_cfg = hw.setdefault("mensor", {})
    if config.get("quality", {}).get("hardware_discovery", {}).get("enable_serial_auto_discovery", True):
        for logical_port, com_port in discover_alicat_assignments(config).items():
            (port_a_cfg if logical_port == "port_a" else port_b_cfg)["com_port"] = com_port
        discovered_mensor = discover_mensor_port(
            config,
            exclude_ports={
                str(port_a_cfg.get("com_port", "")).strip(),
                str(port_b_cfg.get("com_port", "")).strip(),
            },
        )
        if discovered_mensor:
            mensor_cfg["port"] = discovered_mensor

    port_manager = PortManager(config)
    port_manager.initialize_ports()
    port_manager.connect_all()
    port = port_manager.get_port(args.port)
    if port is None:
        logger.error("Port %s not available", args.port)
        return 1

    mensor = MensorReader(mensor_cfg)
    if not mensor.connect():
        logger.error("Mensor failed to connect")
        port_manager.disconnect_all()
        return 1

    cancel = threading.Event()
    sample_period = 1.0 / max(args.rate, 0.5)
    csv_path = args.csv
    if csv_path:
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        file_exists = csv_path.exists()
        f = open(csv_path, "a", newline="", encoding="utf-8")
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(
                ["timestamp_utc", "elapsed_s", "target_psia", "alicat_psia", "mensor_psia", "transducer_psia", "mensor_raw"]
            )

    try:
        last_barometric = 14.7
        print("target_psia,alicat_psia,mensor_psia,transducer_psia,mensor_raw")
        for target_psia in args.points:
            print(f"\n--- Setpoint {target_psia:.1f} psia ---")
            route_ok, route, last_barometric = prepare_port_for_target(
                port, target_psia, last_barometric, cancel
            )
            if not route_ok:
                logger.error("Failed to route for %.1f psia", target_psia)
                continue
            command_target_pressure(port, target_psia, ramp_rate_psi_per_s=8.0)
            try:
                stabilized = wait_until_near_target(
                    port=port,
                    target_psia=target_psia,
                    tolerance_psia=settings.settle_tolerance_psia,
                    hold_s=min(2.0, settings.settle_hold_s),
                    timeout_s=min(30.0, settings.settle_timeout_s),
                    sample_hz=settings.sample_hz,
                    cancel_event=cancel,
                    progress_callback=lambda msg: logger.info("%s", msg),
                )
                last_barometric = stabilized.barometric_psia
            except TimeoutError as e:
                logger.warning("Settle timeout: %s; continuing to sample", e)

            hold_start = time.perf_counter()
            while time.perf_counter() - hold_start < args.hold:
                reading = port.read_all()
                baro = infer_barometric_psia(reading) or last_barometric
                alicat_psia = alicat_abs_psia(reading, baro)
                transducer_psia = transducer_abs_psia(reading, baro)
                mensor_psia = None
                mensor_raw = ""
                try:
                    r = mensor.read_pressure()
                    mensor_psia = r.pressure_psia
                    tail = getattr(mensor, "response_tail", [])
                    mensor_raw = tail[-1] if tail else ""
                except Exception as e:
                    mensor_raw = str(e)
                elapsed = time.perf_counter() - hold_start
                ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                a = f"{alicat_psia:.3f}" if alicat_psia is not None else ""
                m = f"{mensor_psia:.3f}" if mensor_psia is not None else ""
                t = f"{transducer_psia:.3f}" if transducer_psia is not None else ""
                line = f"{target_psia:.1f},{a},{m},{t},{mensor_raw!r}"
                print(line)
                if csv_path:
                    writer.writerow(
                        [ts, f"{elapsed:.2f}", target_psia, alicat_psia, mensor_psia, transducer_psia, mensor_raw]
                    )
                    f.flush()
                time.sleep(sample_period)

            # Log tail of raw Mensor responses at this setpoint
            tail = getattr(mensor, "response_tail", [])
            if tail:
                logger.info("Mensor raw tail at %.1f psia (last 5): %s", target_psia, tail[-5:])
    except KeyboardInterrupt:
        logger.info("Interrupted")
    finally:
        if getattr(args, "_out_file", None) is not None:
            sys.stdout = sys.__stdout__
            args._out_file.close()
            logger.info("Wrote output to %s", getattr(args, "_out_path", args.out))
        if csv_path:
            f.close()
            logger.info("Wrote tail to %s", csv_path)
        try:
            port.vent_to_atmosphere()
        except Exception as e:
            logger.warning("Vent failed: %s", e)
        mensor.close()
        port_manager.disconnect_all()

    return 0


if __name__ == "__main__":
    import traceback as _tb
    try:
        sys.exit(main())
    except Exception:
        _tb.print_exc()
        if getattr(sys, "_sweep_out_file", None) is not None:
            sys._sweep_out_file.write(_tb.format_exc())
            sys._sweep_out_file.flush()
        sys.exit(1)
