"""
Pressure switch sweep test (drives pressure and logs NO/NC transitions).

Usage:
    # Preferred: consolidated hardware CLI
    python scripts/hardware.py switch-sweep --port port_a --com-dio 3 --start 15 --end 50

    # Backwards-compatible direct entry point
    python scripts/pressure_switch_sweep_test.py --port port_a --com-dio 3 --no-dio 0 --nc-dio 2
    python scripts/pressure_switch_sweep_test.py --port port_b --com-dio 12 --no-dio 9 --nc-dio 11
"""

from __future__ import annotations

import argparse
import csv
import logging
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import get_port_config, load_config
from app.hardware.alicat import AlicatController
from app.hardware.labjack import LabJackController

try:
    from labjack import ljm
except Exception:
    ljm = None


@dataclass
class SweepReading:
    timestamp: float
    elapsed_time: float
    phase: str
    transducer_voltage: float
    transducer_pressure_calc: float
    alicat_pressure: float
    no_active: bool
    nc_active: bool
    switch_activated: bool
    com_state: int


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


def read_raw_transducer(labjack: LabJackController) -> Optional[tuple[float, float]]:
    if not labjack.hardware_available():
        return 0.976, 14.7
    if labjack.transducer_ain is None:
        return None
    handle = labjack._shared_handle
    if handle is None:
        return None
    try:
        if ljm is None:
            return None
        voltage = ljm.eReadName(handle, f"AIN{labjack.transducer_ain}")
        voltage_range = labjack.voltage_max - labjack.voltage_min
        pressure_range = labjack.pressure_max - labjack.pressure_min
        if voltage_range > 0:
            pressure_calc = (
                (voltage - labjack.voltage_min) / voltage_range * pressure_range
                + labjack.pressure_min
            )
        else:
            pressure_calc = labjack.pressure_min
        return voltage, pressure_calc
    except Exception:
        return None


def wait_for_pressure(alicat: AlicatController, target: float, tolerance: float = 2.0, timeout_s: float = 30.0) -> None:
    start = time.perf_counter()
    while time.perf_counter() - start < timeout_s:
        status = alicat.read_status()
        if status and abs(status.pressure - target) <= tolerance:
            return
        time.sleep(0.1)


def run_sweep(
    labjack: LabJackController,
    alicat: AlicatController,
    start_pressure: float,
    end_pressure: float,
    rate_psi_s: float,
    settle_time: float,
    hold_time: float,
    sample_hz: float,
    alicat_hz: float,
    com_state: int,
) -> list[SweepReading]:
    readings: list[SweepReading] = []
    sample_period = 1.0 / sample_hz
    alicat_period = 1.0 / alicat_hz
    last_alicat_time = 0.0
    last_alicat_status = None
    start_time = time.perf_counter()

    alicat.cancel_hold()
    time.sleep(0.1)
    alicat.set_ramp_rate(0, time_unit="s")
    time.sleep(0.1)
    alicat.set_pressure(start_pressure)
    wait_for_pressure(alicat, start_pressure)

    settle_start = time.perf_counter()
    while time.perf_counter() - settle_start < settle_time:
        now = time.perf_counter()
        if now - last_alicat_time >= alicat_period:
            last_alicat_status = alicat.read_status()
            last_alicat_time = now
        trans_data = read_raw_transducer(labjack)
        switch_state = labjack.read_switch_state()
        if trans_data and last_alicat_status and switch_state:
            voltage, pressure_calc = trans_data
            readings.append(
                SweepReading(
                    timestamp=now,
                    elapsed_time=now - start_time,
                    phase="settle_start",
                    transducer_voltage=voltage,
                    transducer_pressure_calc=pressure_calc,
                    alicat_pressure=last_alicat_status.pressure,
                    no_active=switch_state.no_active,
                    nc_active=switch_state.nc_active,
                    switch_activated=switch_state.switch_activated,
                    com_state=com_state,
                )
            )
        time.sleep(sample_period)

    alicat.set_ramp_rate(rate_psi_s, time_unit="s")
    alicat.set_pressure(end_pressure)
    pressure_delta = abs(end_pressure - start_pressure)
    expected_duration = pressure_delta / rate_psi_s if rate_psi_s > 0 else 10.0
    timeout_s = expected_duration + 10.0
    ramp_start = time.perf_counter()
    last_state = None

    while True:
        now = time.perf_counter()
        if now - last_alicat_time >= alicat_period:
            last_alicat_status = alicat.read_status()
            last_alicat_time = now
        trans_data = read_raw_transducer(labjack)
        switch_state = labjack.read_switch_state()
        if trans_data and last_alicat_status and switch_state:
            voltage, pressure_calc = trans_data
            readings.append(
                SweepReading(
                    timestamp=now,
                    elapsed_time=now - start_time,
                    phase="ramping",
                    transducer_voltage=voltage,
                    transducer_pressure_calc=pressure_calc,
                    alicat_pressure=last_alicat_status.pressure,
                    no_active=switch_state.no_active,
                    nc_active=switch_state.nc_active,
                    switch_activated=switch_state.switch_activated,
                    com_state=com_state,
                )
            )

            if last_state is not None and switch_state.switch_activated != last_state:
                print(f"  [EDGE] switch_activated={switch_state.switch_activated} at {last_alicat_status.pressure:.2f} PSIA")
            last_state = switch_state.switch_activated

            if abs(last_alicat_status.pressure - end_pressure) < 1.0:
                break

        if now - ramp_start > timeout_s:
            print("  [WARNING] Ramp timeout")
            break

        time.sleep(sample_period)

    hold_start = time.perf_counter()
    while time.perf_counter() - hold_start < hold_time:
        now = time.perf_counter()
        if now - last_alicat_time >= alicat_period:
            last_alicat_status = alicat.read_status()
            last_alicat_time = now
        trans_data = read_raw_transducer(labjack)
        switch_state = labjack.read_switch_state()
        if trans_data and last_alicat_status and switch_state:
            voltage, pressure_calc = trans_data
            readings.append(
                SweepReading(
                    timestamp=now,
                    elapsed_time=now - start_time,
                    phase="hold_end",
                    transducer_voltage=voltage,
                    transducer_pressure_calc=pressure_calc,
                    alicat_pressure=last_alicat_status.pressure,
                    no_active=switch_state.no_active,
                    nc_active=switch_state.nc_active,
                    switch_activated=switch_state.switch_activated,
                    com_state=com_state,
                )
            )
        time.sleep(sample_period)

    return readings


def save_readings(readings: list[SweepReading], output_file: Path, metadata: dict) -> None:
    with output_file.open("w", newline="") as f:
        writer = csv.writer(f)
        for key, value in metadata.items():
            writer.writerow([f"# {key}: {value}"])
        writer.writerow([])
        writer.writerow([
            "timestamp",
            "elapsed_time",
            "phase",
            "transducer_voltage",
            "transducer_pressure_calc",
            "alicat_pressure",
            "no_active",
            "nc_active",
            "switch_activated",
            "com_state",
        ])
        for r in readings:
            writer.writerow([
                r.timestamp,
                r.elapsed_time,
                r.phase,
                r.transducer_voltage,
                r.transducer_pressure_calc,
                r.alicat_pressure,
                r.no_active,
                r.nc_active,
                r.switch_activated,
                r.com_state,
            ])


def main() -> int:
    parser = argparse.ArgumentParser(description="Pressure switch sweep test")
    parser.add_argument(
        '--allow-legacy',
        action='store_true',
        help='Temporarily allow deprecated direct script execution.',
    )
    parser.add_argument("--port", choices=["port_a", "port_b"], default="port_a")
    parser.add_argument("--com-dio", type=int, required=True)
    parser.add_argument("--no-dio", type=int, default=None)
    parser.add_argument("--nc-dio", type=int, default=None)
    parser.add_argument("--start", type=float, default=15.0)
    parser.add_argument("--end", type=float, default=50.0)
    parser.add_argument("--rate", type=float, default=1.0)
    parser.add_argument("--settle", type=float, default=3.0)
    parser.add_argument("--hold", type=float, default=3.0)
    parser.add_argument("--sample-hz", type=float, default=50.0)
    parser.add_argument("--alicat-hz", type=float, default=10.0)
    parser.add_argument("--output-dir", type=str, default="scripts/data")
    parser.add_argument("--com-high", action="store_true", help="Drive COM high instead of low")
    args = parser.parse_args()

    if not args.allow_legacy:
        print('[ERROR] Direct script execution is deprecated.')
        print('Use: python scripts/hardware.py switch-sweep ...')
        print('If you must run this script directly, add --allow-legacy.')
        return 2

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    config = load_config()
    port_cfg = get_port_config(config, args.port)
    lj_cfg = {**config["hardware"]["labjack"], **port_cfg["labjack"]}
    alicat_cfg = {**config["hardware"]["alicat"], **port_cfg["alicat"]}

    no_dio = args.no_dio if args.no_dio is not None else lj_cfg.get("switch_no_dio")
    nc_dio = args.nc_dio if args.nc_dio is not None else lj_cfg.get("switch_nc_dio")
    com_dio = args.com_dio if args.com_dio is not None else lj_cfg.get("switch_com_dio")

    if no_dio is None or nc_dio is None:
        print("[FAIL] NO/NC DIO pins are not configured. Use --no-dio/--nc-dio.")
        return 1

    if com_dio is None:
        print("[FAIL] COM DIO pin is not configured. Use --com-dio.")
        return 1

    labjack = LabJackController(lj_cfg)
    if not labjack.configure():
        print(f"[FAIL] LabJack configuration failed: {labjack._last_status}")
        return 1
    # Configure NO/NC as inputs and COM as output (high by default, can be changed by --com-high flag)
    com_state = 1 if args.com_high else 0
    labjack.configure_di_pins(no_dio, nc_dio, com_dio, com_state=com_state)

    alicat = AlicatController(alicat_cfg)
    if not alicat.connect():
        print(f"[FAIL] Alicat connection failed: {alicat._last_status}")
        labjack.cleanup()
        return 1

    com_state = 1 if args.com_high else 0
    if not _set_com_state(labjack, args.com_dio, high=args.com_high):
        print("[WARNING] Could not set COM state")

    print("\n=== PRESSURE SWITCH SWEEP ===")
    print(f"Port: {args.port}")
    print(f"NO DIO: {no_dio} | NC DIO: {nc_dio} | COM DIO: {args.com_dio}")
    print(f"Sweep: {args.start:.1f} -> {args.end:.1f} PSIA at {args.rate:.2f} PSI/s")

    try:
        readings = run_sweep(
            labjack=labjack,
            alicat=alicat,
            start_pressure=args.start,
            end_pressure=args.end,
            rate_psi_s=args.rate,
            settle_time=args.settle,
            hold_time=args.hold,
            sample_hz=args.sample_hz,
            alicat_hz=args.alicat_hz,
            com_state=com_state,
        )
    finally:
        _set_com_state(labjack, args.com_dio, high=False)
        alicat.exhaust()
        time.sleep(1.0)
        alicat.disconnect()
        labjack.cleanup()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    output_file = output_dir / f"switch_sweep_{args.port}_{timestamp}.csv"
    metadata = {
        "port": args.port,
        "start_pressure_psia": args.start,
        "end_pressure_psia": args.end,
        "rate_psi_s": args.rate,
        "no_dio": no_dio,
        "nc_dio": nc_dio,
        "com_dio": args.com_dio,
    }
    save_readings(readings, output_file, metadata)
    print(f"\nData saved to: {output_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
