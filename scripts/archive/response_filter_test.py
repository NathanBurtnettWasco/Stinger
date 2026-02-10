"""
Transducer response vs noise filter sweep.

Runs a step sequence and evaluates filter tradeoffs offline.

Usage:
    python response_filter_test.py --port port_a --output-dir scripts/data
"""

from __future__ import annotations

import argparse
import csv
import logging
import math
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import load_config
from app.hardware.alicat import AlicatController
from app.hardware.labjack import LabJackController

try:
    from labjack import ljm
except Exception:
    ljm = None


@dataclass
class StepReading:
    timestamp: float
    elapsed_time: float
    phase: str
    transducer_pressure: float
    alicat_pressure: float
    alicat_setpoint: float


def read_raw_transducer(labjack: LabJackController) -> Optional[float]:
    if not labjack.hardware_available():
        return 14.7
    if labjack.transducer_ain is None:
        return None
    handle = labjack._shared_handle
    if handle is None:
        return None
    if ljm is None:
        return None
    try:
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
        return pressure_calc
    except Exception:
        return None


def _moving_average(values: np.ndarray, window: int) -> np.ndarray:
    if window <= 1:
        return values
    kernel = np.ones(window) / window
    return np.convolve(values, kernel, mode="same")


def _exp_smooth(values: np.ndarray, alpha: float) -> np.ndarray:
    if not values.size:
        return values
    output = np.empty_like(values)
    output[0] = values[0]
    for i in range(1, len(values)):
        output[i] = alpha * values[i] + (1 - alpha) * output[i - 1]
    return output


def _median_filter(values: np.ndarray, window: int) -> np.ndarray:
    if window <= 1:
        return values
    output = np.empty_like(values)
    half = window // 2
    for i in range(len(values)):
        start = max(0, i - half)
        end = min(len(values), i + half + 1)
        output[i] = float(np.median(values[start:end]))
    return output


def _estimate_dt(times: List[float]) -> float:
    if len(times) < 2:
        return 0.0
    diffs = np.diff(np.array(times))
    diffs = diffs[diffs > 0]
    return float(np.median(diffs)) if diffs.size else 0.0


def _best_lag_seconds(raw: np.ndarray, filtered: np.ndarray, dt: float, max_lag_s: float = 2.0) -> float:
    if dt <= 0:
        return 0.0
    max_lag_samples = int(max_lag_s / dt)
    best_lag = 0
    best_err = math.inf
    for lag in range(0, max_lag_samples + 1):
        shifted = filtered[lag:]
        target = raw[: len(shifted)]
        if shifted.size == 0:
            break
        err = float(np.mean((target - shifted) ** 2))
        if err < best_err:
            best_err = err
            best_lag = lag
    return best_lag * dt


def run_step_sequence(
    labjack: LabJackController,
    alicat: AlicatController,
    low: float,
    high: float,
    rate: float,
    hold_s: float,
    cycles: int,
    sample_hz: float,
    alicat_hz: float,
) -> List[StepReading]:
    readings: List[StepReading] = []
    sample_period = 1.0 / sample_hz
    alicat_period = 1.0 / alicat_hz
    last_alicat_time = 0.0
    last_alicat_status = None

    alicat.cancel_hold()
    time.sleep(0.1)
    alicat.set_ramp_rate(0, time_unit="s")
    alicat.set_pressure(low)
    time.sleep(1.0)

    start_time = time.perf_counter()

    def record(phase: str, duration_s: float) -> None:
        nonlocal last_alicat_time, last_alicat_status
        end_time = time.perf_counter() + duration_s
        while time.perf_counter() < end_time:
            now = time.perf_counter()
            if now - last_alicat_time >= alicat_period:
                last_alicat_status = alicat.read_status()
                last_alicat_time = now
            trans = read_raw_transducer(labjack)
            if trans is not None and last_alicat_status is not None:
                readings.append(
                    StepReading(
                        timestamp=now,
                        elapsed_time=now - start_time,
                        phase=phase,
                        transducer_pressure=trans,
                        alicat_pressure=last_alicat_status.pressure,
                        alicat_setpoint=last_alicat_status.setpoint or 0.0,
                    )
                )
            time.sleep(sample_period)

    for cycle in range(cycles):
        alicat.set_ramp_rate(rate, time_unit="s")
        alicat.set_pressure(high)
        record(f"ramp_up_{cycle + 1}", abs(high - low) / rate + 1.0)
        record(f"hold_high_{cycle + 1}", hold_s)

        alicat.set_ramp_rate(rate, time_unit="s")
        alicat.set_pressure(low)
        record(f"ramp_down_{cycle + 1}", abs(high - low) / rate + 1.0)
        record(f"hold_low_{cycle + 1}", hold_s)

    return readings


def evaluate_filters(readings: List[StepReading], output_dir: Path) -> None:
    if not readings:
        return

    times = [r.elapsed_time for r in readings]
    trans = np.array([r.transducer_pressure for r in readings])
    alicat = np.array([r.alicat_pressure for r in readings])
    phases = [r.phase for r in readings]
    dt = _estimate_dt(times)

    holds = [(i, p) for i, p in enumerate(phases) if p.startswith("hold")]
    hold_indices = [i for i, _ in holds]

    candidates = []
    for window_s in [0.02, 0.05, 0.1, 0.2, 0.5]:
        candidates.append(("moving_average", window_s))
        candidates.append(("median", window_s))
    for alpha in [0.05, 0.1, 0.2, 0.3, 0.5]:
        candidates.append(("exponential", alpha))

    rows = []
    for kind, param in candidates:
        if kind == "moving_average":
            window = max(1, int(param / dt)) if dt > 0 else 1
            filtered = _moving_average(trans, window)
        elif kind == "median":
            window = max(1, int(param / dt)) if dt > 0 else 1
            filtered = _median_filter(trans, window)
        else:
            filtered = _exp_smooth(trans, param)

        noise_std = float(np.std(filtered[hold_indices])) if hold_indices else math.nan

        ramp_indices = [i for i, p in enumerate(phases) if p.startswith("ramp")]
        response_time = math.nan
        if ramp_indices:
            ramp_filtered = filtered[ramp_indices]
            ramp_alicat = alicat[ramp_indices]
            response_time = _best_lag_seconds(ramp_alicat, ramp_filtered, dt)
        rows.append({
            "kind": kind,
            "param": param,
            "noise_std_psi": noise_std,
            "response_time_s": response_time,
        })

    rows.sort(key=lambda r: (r["response_time_s"], r["noise_std_psi"]))

    report_path = output_dir / "filter_response_report.csv"
    with report_path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["kind", "param", "noise_std_psi", "response_time_s"])
        for row in rows:
            writer.writerow([row["kind"], row["param"], row["noise_std_psi"], row["response_time_s"]])


def save_readings(readings: List[StepReading], output_file: Path, metadata: dict) -> None:
    with output_file.open("w", newline="") as f:
        writer = csv.writer(f)
        for key, value in metadata.items():
            writer.writerow([f"# {key}: {value}"])
        writer.writerow([])
        writer.writerow([
            "timestamp",
            "elapsed_time",
            "phase",
            "transducer_pressure",
            "alicat_pressure",
            "alicat_setpoint",
        ])
        for r in readings:
            writer.writerow([
                r.timestamp,
                r.elapsed_time,
                r.phase,
                r.transducer_pressure,
                r.alicat_pressure,
                r.alicat_setpoint,
            ])


def main() -> int:
    parser = argparse.ArgumentParser(description="Transducer response vs noise filter sweep")
    parser.add_argument("--port", choices=["port_a", "port_b"], default="port_a")
    parser.add_argument("--low", type=float, default=15.0)
    parser.add_argument("--high", type=float, default=50.0)
    parser.add_argument("--rate", type=float, default=10.0)
    parser.add_argument("--hold", type=float, default=3.0)
    parser.add_argument("--cycles", type=int, default=3)
    parser.add_argument("--sample-hz", type=float, default=50.0)
    parser.add_argument("--alicat-hz", type=float, default=10.0)
    parser.add_argument("--output-dir", type=str, default="scripts/data")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    config = load_config()
    lj_cfg = {**config["hardware"]["labjack"], **config["hardware"]["labjack"].get(args.port, {})}
    alicat_cfg = {**config["hardware"]["alicat"], **config["hardware"]["alicat"].get(args.port, {})}

    labjack = LabJackController(lj_cfg)
    if not labjack.configure():
        print(f"[FAIL] LabJack configuration failed: {labjack._last_status}")
        return 1

    alicat = AlicatController(alicat_cfg)
    if not alicat.connect():
        print(f"[FAIL] Alicat connection failed: {alicat._last_status}")
        labjack.cleanup()
        return 1

    try:
        readings = run_step_sequence(
            labjack=labjack,
            alicat=alicat,
            low=args.low,
            high=args.high,
            rate=args.rate,
            hold_s=args.hold,
            cycles=args.cycles,
            sample_hz=args.sample_hz,
            alicat_hz=args.alicat_hz,
        )
    finally:
        alicat.exhaust()
        time.sleep(1.0)
        alicat.disconnect()
        labjack.cleanup()

    output_dir = Path(args.output_dir) / f"response_filter_{time.strftime('%Y%m%d_%H%M%S')}"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"response_filter_{args.port}.csv"
    metadata = {
        "port": args.port,
        "low_psia": args.low,
        "high_psia": args.high,
        "rate_psi_s": args.rate,
        "hold_s": args.hold,
        "cycles": args.cycles,
    }
    save_readings(readings, output_file, metadata)
    evaluate_filters(readings, output_dir)
    print(f"Data saved to: {output_file}")
    print(f"Filter report: {output_dir / 'filter_response_report.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
