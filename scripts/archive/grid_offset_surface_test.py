"""
Grid Offset Surface Test - Run a pressure/rate grid and capture offsets.

Usage:
    python scripts/grid_offset_surface_test.py --port port_a --output-dir scripts/data/20260203
"""

from __future__ import annotations

import argparse
import csv
import logging
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import load_config
from app.hardware.alicat import AlicatController
from app.hardware.labjack import LabJackController


@dataclass
class GridReading:
    timestamp: float
    elapsed_time: float
    phase: str
    transducer_voltage: float
    transducer_pressure_calc: float
    alicat_pressure: float
    alicat_setpoint: float
    alicat_gauge: float
    alicat_baro: Optional[float]
    ramp_rate_commanded: float
    target_pressure: float
    direction: str
    step_index: int
    rate_index: int


@dataclass
class StepSummary:
    port: str
    rate_psi_s: float
    target_pressure_psia: float
    direction: str
    step_index: int
    ramp_mean_offset_psi: float
    ramp_std_offset_psi: float
    ramp_samples: int
    hold_mean_offset_psi: float
    hold_std_offset_psi: float
    hold_samples: int
    ramp_start_pressure: float
    ramp_end_pressure: float
    ramp_duration_s: float
    hold_duration_s: float


def read_raw_transducer(labjack: LabJackController) -> Optional[tuple[float, float]]:
    """Read transducer voltage and calculated pressure (no offset, no filter)."""
    if not labjack.hardware_available():
        return 0.976, 14.7

    if labjack.transducer_ain is None:
        return None

    handle = labjack._shared_handle
    if handle is None:
        return None

    try:
        from labjack import ljm

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


def wait_for_pressure(
    alicat: AlicatController,
    target: float,
    tolerance: float = 2.0,
    timeout_s: float = 30.0,
) -> Optional[float]:
    start = time.perf_counter()
    last_pressure = None
    while time.perf_counter() - start < timeout_s:
        status = alicat.read_status()
        if status:
            last_pressure = status.pressure
            if abs(status.pressure - target) <= tolerance:
                return status.pressure
        time.sleep(0.1)
    return last_pressure


def sample_loop(
    labjack: LabJackController,
    alicat: AlicatController,
    readings: List[GridReading],
    phase: str,
    start_time: float,
    duration_s: float,
    ramp_rate: float,
    target_pressure: float,
    direction: str,
    step_index: int,
    rate_index: int,
    sample_period_s: float,
    alicat_period_s: float,
    last_alicat_time: float,
    last_alicat_status,
) -> tuple[float, Optional[object]]:
    end_time = time.perf_counter() + duration_s
    while time.perf_counter() < end_time:
        now = time.perf_counter()
        if now - last_alicat_time >= alicat_period_s:
            last_alicat_status = alicat.read_status()
            last_alicat_time = now

        trans_data = read_raw_transducer(labjack)
        status = last_alicat_status
        if trans_data and status:
            voltage, pressure_calc = trans_data
            baro = status.barometric_pressure or 14.7
            readings.append(
                GridReading(
                    timestamp=now,
                    elapsed_time=now - start_time,
                    phase=phase,
                    transducer_voltage=voltage,
                    transducer_pressure_calc=pressure_calc,
                    alicat_pressure=status.pressure,
                    alicat_setpoint=status.setpoint or 0.0,
                    alicat_gauge=status.pressure - baro,
                    alicat_baro=status.barometric_pressure,
                    ramp_rate_commanded=ramp_rate,
                    target_pressure=target_pressure,
                    direction=direction,
                    step_index=step_index,
                    rate_index=rate_index,
                )
            )

        time.sleep(sample_period_s)

    return last_alicat_time, last_alicat_status


def run_grid_test(
    port: str,
    labjack: LabJackController,
    alicat: AlicatController,
    pressures: List[float],
    rates: List[float],
    settle_time_s: float,
    hold_time_s: float,
    sweep: str,
    sample_hz: float,
    alicat_hz: float,
) -> tuple[List[GridReading], List[StepSummary]]:
    readings: List[GridReading] = []
    summaries: List[StepSummary] = []

    sample_period_s = 1.0 / sample_hz
    alicat_period_s = 1.0 / alicat_hz

    start_time = time.perf_counter()
    last_alicat_time = 0.0
    last_alicat_status = None

    print("\n" + "=" * 70)
    print("GRID OFFSET SURFACE TEST")
    print("=" * 70)
    print(f"Port: {port}")
    print(f"Pressures: {pressures[0]:.1f} -> {pressures[-1]:.1f} PSIA ({len(pressures)} steps)")
    print(f"Rates: {rates[0]:.2f} -> {rates[-1]:.2f} PSI/s ({len(rates)} steps)")
    print(f"Sweep: {sweep}")
    print(f"Hold time: {hold_time_s:.1f}s | Settle time: {settle_time_s:.1f}s")
    print("=" * 70)

    for rate_index, rate in enumerate(rates):
        print(f"\n--- Rate {rate:.2f} PSI/s ({rate_index + 1}/{len(rates)}) ---")

        alicat.cancel_hold()
        time.sleep(0.1)
        alicat.set_ramp_rate(0, time_unit="s")
        time.sleep(0.1)

        start_pressure = pressures[0]
        alicat.set_pressure(start_pressure)
        reached = wait_for_pressure(alicat, start_pressure, tolerance=2.0, timeout_s=30.0)
        if reached is None:
            print("  [WARNING] Timeout waiting for start pressure")

        last_alicat_time, last_alicat_status = sample_loop(
            labjack=labjack,
            alicat=alicat,
            readings=readings,
            phase="settle_start",
            start_time=start_time,
            duration_s=settle_time_s,
            ramp_rate=0.0,
            target_pressure=start_pressure,
            direction="up",
            step_index=0,
            rate_index=rate_index,
            sample_period_s=sample_period_s,
            alicat_period_s=alicat_period_s,
            last_alicat_time=last_alicat_time,
            last_alicat_status=last_alicat_status,
        )

        sweeps = [("up", pressures)]
        if sweep == "up_down":
            sweeps.append(("down", list(reversed(pressures))))

        step_counter = 0
        for direction, sequence in sweeps:
            for target in sequence:
                step_counter += 1
                if last_alicat_status:
                    current_pressure = last_alicat_status.pressure
                else:
                    current_pressure = target

                ramp_offsets: List[float] = []
                hold_offsets: List[float] = []
                ramp_start_pressure = current_pressure

                if abs(current_pressure - target) > 0.1:
                    alicat.set_ramp_rate(rate, time_unit="s")
                    alicat.set_pressure(target)

                    expected_duration = abs(target - current_pressure) / rate if rate > 0 else 10.0
                    timeout_s = expected_duration + 10.0
                    ramp_start_time = time.perf_counter()
                    ramp_end_time = ramp_start_time

                    while True:
                        now = time.perf_counter()
                        if now - last_alicat_time >= alicat_period_s:
                            last_alicat_status = alicat.read_status()
                            last_alicat_time = now

                        trans_data = read_raw_transducer(labjack)
                        status = last_alicat_status
                        if trans_data and status:
                            voltage, pressure_calc = trans_data
                            baro = status.barometric_pressure or 14.7
                            readings.append(
                                GridReading(
                                    timestamp=now,
                                    elapsed_time=now - start_time,
                                    phase="ramping",
                                    transducer_voltage=voltage,
                                    transducer_pressure_calc=pressure_calc,
                                    alicat_pressure=status.pressure,
                                    alicat_setpoint=status.setpoint or 0.0,
                                    alicat_gauge=status.pressure - baro,
                                    alicat_baro=status.barometric_pressure,
                                    ramp_rate_commanded=rate,
                                    target_pressure=target,
                                    direction=direction,
                                    step_index=step_counter,
                                    rate_index=rate_index,
                                )
                            )
                            ramp_offsets.append(pressure_calc - status.pressure)

                            if abs(status.pressure - target) < 1.0:
                                ramp_end_time = now
                                break

                        if now - ramp_start_time > timeout_s:
                            ramp_end_time = now
                            print("  [WARNING] Ramp timeout")
                            break

                        time.sleep(sample_period_s)

                    ramp_duration_s = ramp_end_time - ramp_start_time
                else:
                    ramp_duration_s = 0.0

                ramp_end_pressure = last_alicat_status.pressure if last_alicat_status else target

                last_alicat_time, last_alicat_status = sample_loop(
                    labjack=labjack,
                    alicat=alicat,
                    readings=readings,
                    phase="hold",
                    start_time=start_time,
                    duration_s=hold_time_s,
                    ramp_rate=0.0,
                    target_pressure=target,
                    direction=direction,
                    step_index=step_counter,
                    rate_index=rate_index,
                    sample_period_s=sample_period_s,
                    alicat_period_s=alicat_period_s,
                    last_alicat_time=last_alicat_time,
                    last_alicat_status=last_alicat_status,
                )

                hold_start_idx = len(readings) - int(hold_time_s / sample_period_s)
                if hold_start_idx < 0:
                    hold_start_idx = 0
                for r in readings[hold_start_idx:]:
                    if r.phase == "hold" and r.step_index == step_counter:
                        hold_offsets.append(r.transducer_pressure_calc - r.alicat_pressure)

                ramp_mean = float(np.mean(ramp_offsets)) if ramp_offsets else float("nan")
                ramp_std = float(np.std(ramp_offsets)) if ramp_offsets else float("nan")
                hold_mean = float(np.mean(hold_offsets)) if hold_offsets else float("nan")
                hold_std = float(np.std(hold_offsets)) if hold_offsets else float("nan")

                summaries.append(
                    StepSummary(
                        port=port,
                        rate_psi_s=rate,
                        target_pressure_psia=target,
                        direction=direction,
                        step_index=step_counter,
                        ramp_mean_offset_psi=ramp_mean,
                        ramp_std_offset_psi=ramp_std,
                        ramp_samples=len(ramp_offsets),
                        hold_mean_offset_psi=hold_mean,
                        hold_std_offset_psi=hold_std,
                        hold_samples=len(hold_offsets),
                        ramp_start_pressure=ramp_start_pressure,
                        ramp_end_pressure=ramp_end_pressure,
                        ramp_duration_s=ramp_duration_s,
                        hold_duration_s=hold_time_s,
                    )
                )

    return readings, summaries


def save_grid_samples(readings: List[GridReading], output_file: Path, metadata: Dict) -> None:
    with output_file.open("w", newline="") as f:
        writer = csv.writer(f)
        for key, value in metadata.items():
            writer.writerow([f"# {key}: {value}"])
        writer.writerow([])
        writer.writerow(
            [
                "timestamp",
                "elapsed_time",
                "phase",
                "transducer_voltage",
                "transducer_pressure_calc",
                "alicat_pressure",
                "alicat_setpoint",
                "alicat_gauge",
                "alicat_baro",
                "ramp_rate_commanded",
                "target_pressure",
                "direction",
                "step_index",
                "rate_index",
                "offset_calc",
            ]
        )
        for r in readings:
            offset = r.transducer_pressure_calc - r.alicat_pressure
            writer.writerow(
                [
                    r.timestamp,
                    r.elapsed_time,
                    r.phase,
                    r.transducer_voltage,
                    r.transducer_pressure_calc,
                    r.alicat_pressure,
                    r.alicat_setpoint,
                    r.alicat_gauge,
                    r.alicat_baro,
                    r.ramp_rate_commanded,
                    r.target_pressure,
                    r.direction,
                    r.step_index,
                    r.rate_index,
                    offset,
                ]
            )


def save_grid_summary(summaries: List[StepSummary], output_file: Path, metadata: Dict) -> None:
    with output_file.open("w", newline="") as f:
        writer = csv.writer(f)
        for key, value in metadata.items():
            writer.writerow([f"# {key}: {value}"])
        writer.writerow([])
        writer.writerow(
            [
                "port",
                "rate_psi_s",
                "target_pressure_psia",
                "direction",
                "step_index",
                "ramp_mean_offset_psi",
                "ramp_std_offset_psi",
                "ramp_samples",
                "hold_mean_offset_psi",
                "hold_std_offset_psi",
                "hold_samples",
                "ramp_start_pressure_psia",
                "ramp_end_pressure_psia",
                "ramp_duration_s",
                "hold_duration_s",
            ]
        )
        for s in summaries:
            writer.writerow(
                [
                    s.port,
                    s.rate_psi_s,
                    s.target_pressure_psia,
                    s.direction,
                    s.step_index,
                    s.ramp_mean_offset_psi,
                    s.ramp_std_offset_psi,
                    s.ramp_samples,
                    s.hold_mean_offset_psi,
                    s.hold_std_offset_psi,
                    s.hold_samples,
                    s.ramp_start_pressure,
                    s.ramp_end_pressure,
                    s.ramp_duration_s,
                    s.hold_duration_s,
                ]
            )


def main() -> int:
    parser = argparse.ArgumentParser(description="Grid offset surface test")
    parser.add_argument("--port", choices=["port_a", "port_b"], default="port_a")
    parser.add_argument("--min-pressure", type=float, default=15.0)
    parser.add_argument("--max-pressure", type=float, default=50.0)
    parser.add_argument("--pressure-steps", type=int, default=10)
    parser.add_argument("--min-rate", type=float, default=0.1)
    parser.add_argument("--max-rate", type=float, default=5.0)
    parser.add_argument("--rate-steps", type=int, default=10)
    parser.add_argument("--hold", type=float, default=5.0)
    parser.add_argument("--settle", type=float, default=3.0)
    parser.add_argument("--sweep", choices=["up", "up_down"], default="up_down")
    parser.add_argument("--sample-hz", type=float, default=50.0)
    parser.add_argument("--alicat-hz", type=float, default=10.0)
    parser.add_argument("--output-dir", type=str, default="scripts/data/20260203")
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")

    try:
        config = load_config()
    except Exception as exc:
        print(f"[FAIL] Could not load config: {exc}")
        return 1

    pressures = np.linspace(args.min_pressure, args.max_pressure, args.pressure_steps).tolist()
    rates = np.linspace(args.min_rate, args.max_rate, args.rate_steps).tolist()

    pressures = [max(10.0, min(p, 100.0)) for p in pressures]
    rates = [max(0.01, r) for r in rates]

    labjack_cfg = config.get("hardware", {}).get("labjack", {})
    port_cfg = labjack_cfg.get(args.port, {})

    labjack = LabJackController(
        {
            "device_type": labjack_cfg.get("device_type", "T7"),
            "connection_type": labjack_cfg.get("connection_type", "USB"),
            "identifier": labjack_cfg.get("identifier", "ANY"),
            "transducer_ain": port_cfg.get("transducer_ain"),
            "transducer_ain_neg": port_cfg.get("transducer_ain_neg"),
            "transducer_voltage_min": port_cfg.get("transducer_voltage_min", 0.5),
            "transducer_voltage_max": port_cfg.get("transducer_voltage_max", 4.5),
            "transducer_pressure_min": port_cfg.get("transducer_pressure_min", 0.0),
            "transducer_pressure_max": port_cfg.get("transducer_pressure_max", 115.0),
            "transducer_filter_alpha": 0.0,
            "transducer_reference": port_cfg.get("transducer_reference", "absolute"),
            "transducer_offset_psi": 0.0,
        },
    )

    alicat_cfg = config.get("hardware", {}).get("alicat", {})
    port_alicat_cfg = alicat_cfg.get(args.port, {})
    alicat = AlicatController(
        {
            "com_port": port_alicat_cfg.get("com_port"),
            "address": port_alicat_cfg.get("address"),
            "baudrate": alicat_cfg.get("baudrate", 19200),
            "timeout_s": 0.1,
            "pressure_index": alicat_cfg.get("pressure_index"),
            "setpoint_index": alicat_cfg.get("setpoint_index"),
            "gauge_index": alicat_cfg.get("gauge_index"),
            "barometric_index": alicat_cfg.get("barometric_index"),
        },
    )

    print("\nConnecting to hardware...")
    if not labjack.configure():
        print("[FAIL] LabJack configuration failed")
        return 1

    if not alicat.connect():
        print("[FAIL] Alicat connection failed")
        labjack.cleanup()
        return 1

    try:
        readings, summaries = run_grid_test(
            port=args.port,
            labjack=labjack,
            alicat=alicat,
            pressures=pressures,
            rates=rates,
            settle_time_s=args.settle,
            hold_time_s=args.hold,
            sweep=args.sweep,
            sample_hz=args.sample_hz,
            alicat_hz=args.alicat_hz,
        )

        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        samples_path = output_dir / f"grid_samples_{args.port}_{timestamp}.csv"
        summary_path = output_dir / f"grid_summary_{args.port}_{timestamp}.csv"

        metadata = {
            "port": args.port,
            "pressures": f"{pressures[0]:.2f}-{pressures[-1]:.2f}",
            "pressure_steps": len(pressures),
            "rates": f"{rates[0]:.3f}-{rates[-1]:.3f}",
            "rate_steps": len(rates),
            "hold_time_s": args.hold,
            "settle_time_s": args.settle,
            "sweep": args.sweep,
            "sample_hz": args.sample_hz,
            "alicat_hz": args.alicat_hz,
            "total_samples": len(readings),
            "total_steps": len(summaries),
        }

        save_grid_samples(readings, samples_path, metadata)
        save_grid_summary(summaries, summary_path, metadata)

        print(f"Samples saved to: {samples_path}")
        print(f"Summary saved to: {summary_path}")

    except KeyboardInterrupt:
        print("\nStopped by user")
    except Exception as exc:
        print(f"\n[ERROR] Test failed: {exc}")
        import traceback

        traceback.print_exc()
        return 1
    finally:
        print("\nCleaning up...")
        try:
            alicat.exhaust()
            time.sleep(1.0)
        except Exception:
            pass
        alicat.disconnect()
        labjack.cleanup()

    print("\nGrid test complete!")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
