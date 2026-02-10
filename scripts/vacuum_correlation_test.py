#!/usr/bin/env python3
"""Vacuum correlation test: transducer vs Alicat in vacuum.

Usage:
    python -m scripts.vacuum_correlation_test --port port_a --target-psig -10
    python -m scripts.vacuum_correlation_test --both-ports --target-psig -10
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
from app.hardware.port import Port, PortId


@dataclass
class VacuumReading:
    timestamp: float
    elapsed_time: float
    transducer_psia: float
    alicat_psia: float
    baro_psia: float

    @property
    def transducer_psig(self) -> float:
        return self.transducer_psia - self.baro_psia

    @property
    def alicat_psig(self) -> float:
        return self.alicat_psia - self.baro_psia

    @property
    def offset_abs(self) -> float:
        return self.transducer_psia - self.alicat_psia

    @property
    def offset_gauge(self) -> float:
        return self.transducer_psig - self.alicat_psig


def _build_port(config: dict, port_label: str) -> Port:
    port_cfg = get_port_config(config, port_label)
    labjack_cfg = {**config.get("hardware", {}).get("labjack", {}), **port_cfg.get("labjack", {})}
    alicat_base = config.get("hardware", {}).get("alicat", {})
    alicat_cfg = {
        "com_port": port_cfg.get("alicat", {}).get("com_port"),
        "address": port_cfg.get("alicat", {}).get("address"),
        "baudrate": alicat_base.get("baudrate", 19200),
        "timeout_s": alicat_base.get("timeout_s", 0.05),
        "pressure_index": alicat_base.get("pressure_index"),
        "gauge_index": alicat_base.get("gauge_index"),
        "barometric_index": alicat_base.get("barometric_index"),
        "setpoint_index": alicat_base.get("setpoint_index"),
        "pressure_units_stat": alicat_base.get("pressure_units_stat"),
        "pressure_units_group": alicat_base.get("pressure_units_group"),
        "pressure_units_value": alicat_base.get("pressure_units_value"),
        "pressure_units_override": alicat_base.get("pressure_units_override"),
    }
    solenoid_cfg = config.get("hardware", {}).get("solenoid", {})

    port_id = PortId.PORT_A if port_label == "port_a" else PortId.PORT_B
    return Port(port_id=port_id, labjack_config=labjack_cfg, alicat_config=alicat_cfg, solenoid_config=solenoid_cfg)


def _wait_for_pressure(port: Port, target_psia: float, tolerance: float = 0.3, timeout_s: float = 60.0) -> bool:
    start = time.perf_counter()
    while time.perf_counter() - start < timeout_s:
        reading = port.alicat.read_status()
        if reading and abs(reading.pressure - target_psia) <= tolerance:
            return True
        time.sleep(0.2)
    return False


def _wait_for_atmosphere(port: Port, baro_psia: float, threshold_psig: float, timeout_s: float = 60.0) -> bool:
    start = time.perf_counter()
    while time.perf_counter() - start < timeout_s:
        reading = port.alicat.read_status()
        if reading:
            if abs(reading.pressure - baro_psia) <= threshold_psig:
                return True
        time.sleep(0.2)
    return False


def _collect_reading(port: Port, baro_psia: float, elapsed: float) -> Optional[VacuumReading]:
    transducer = port.daq.read_transducer()
    alicat = port.alicat.read_status()
    if not transducer or not alicat:
        return None
    return VacuumReading(
        timestamp=time.time(),
        elapsed_time=elapsed,
        transducer_psia=transducer.pressure,
        alicat_psia=alicat.pressure,
        baro_psia=alicat.barometric_pressure or baro_psia,
    )


def run_vacuum_test(
    port: Port,
    target_psig: float,
    ramp_rate: float,
    sample_rate_hz: float,
    switch_threshold_psig: float,
) -> list[VacuumReading]:
    readings: list[VacuumReading] = []
    sample_interval = 1.0 / sample_rate_hz

    port.alicat.cancel_hold()
    port.alicat.exhaust()
    time.sleep(2.0)

    status = port.alicat.read_status()
    baro_psia = status.barometric_pressure if status and status.barometric_pressure else 14.7

    port.set_solenoid(to_vacuum=False)
    port.alicat.set_ramp_rate(ramp_rate)
    port.alicat.set_pressure(baro_psia)
    _wait_for_pressure(port, baro_psia, tolerance=0.5, timeout_s=90.0)

    if not _wait_for_atmosphere(port, baro_psia, switch_threshold_psig, timeout_s=30.0):
        print("  [WARNING] Did not stabilize near atmosphere before vacuum.")
    port.set_solenoid(to_vacuum=True)

    target_psia = max(0.5, baro_psia + target_psig)
    port.alicat.set_pressure(target_psia)

    start = time.perf_counter()
    last_sample = start
    last_status = start
    status_interval = 2.0

    while True:
        now = time.perf_counter()
        elapsed = now - start

        if now - last_sample >= sample_interval:
            reading = _collect_reading(port, baro_psia, elapsed)
            if reading:
                readings.append(reading)
            last_sample = now

        if now - last_status >= status_interval and readings:
            latest = readings[-1]
            print(
                f"  [STATUS] t={elapsed:6.1f}s | "
                f"Transducer={latest.transducer_psia:6.2f} PSIA ({latest.transducer_psig:+6.2f} PSIG) | "
                f"Alicat={latest.alicat_psia:6.2f} PSIA ({latest.alicat_psig:+6.2f} PSIG) | "
                f"Offset={latest.offset_abs:+7.4f} PSI"
            )
            last_status = now

        if readings:
            if abs(readings[-1].alicat_psia - target_psia) <= 0.5:
                time.sleep(2.0)
                break

        if elapsed > 120.0:
            print("  [WARNING] Timeout waiting for vacuum target.")
            break

        time.sleep(0.01)

    for _ in range(10):
        time.sleep(sample_interval)
        reading = _collect_reading(port, baro_psia, time.perf_counter() - start)
        if reading:
            readings.append(reading)

    return readings


def _save_csv(readings: list[VacuumReading], output_file: Path, metadata: dict) -> None:
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with output_file.open("w", newline="") as f:
        writer = csv.writer(f)
        for key, value in metadata.items():
            writer.writerow([f"# {key}: {value}"])
        writer.writerow([])
        writer.writerow([
            "timestamp",
            "elapsed_time_s",
            "transducer_psia",
            "alicat_psia",
            "baro_psia",
            "transducer_psig",
            "alicat_psig",
            "offset_abs",
            "offset_gauge",
        ])
        for r in readings:
            writer.writerow([
                r.timestamp,
                r.elapsed_time,
                r.transducer_psia,
                r.alicat_psia,
                r.baro_psia,
                r.transducer_psig,
                r.alicat_psig,
                r.offset_abs,
                r.offset_gauge,
            ])


def _summarize(readings: list[VacuumReading]) -> None:
    if not readings:
        print("  [WARNING] No readings collected.")
        return
    offsets_abs = [r.offset_abs for r in readings]
    offsets_gauge = [r.offset_gauge for r in readings]
    mean_abs = sum(offsets_abs) / len(offsets_abs)
    mean_gauge = sum(offsets_gauge) / len(offsets_gauge)
    print(f"  [SUMMARY] Mean offset (abs): {mean_abs:+.4f} PSI")
    print(f"  [SUMMARY] Mean offset (gauge): {mean_gauge:+.4f} PSI")


def _run_for_port(
    port_label: str,
    target_psig: float,
    ramp_rate: float,
    sample_rate_hz: float,
    switch_threshold_psig: float,
    output_dir: Path,
) -> None:
    config = load_config()
    port = _build_port(config, port_label)

    print("\n" + "=" * 60)
    print(f"Vacuum test: {port_label}")
    print("=" * 60)

    if not port.daq.configure():
        print(f"[FAIL] LabJack configuration failed for {port_label}")
        return
    if not port.alicat.connect():
        print(f"[FAIL] Alicat connection failed for {port_label}")
        port.daq.cleanup()
        return

    try:
        readings = run_vacuum_test(
            port=port,
            target_psig=target_psig,
            ramp_rate=ramp_rate,
            sample_rate_hz=sample_rate_hz,
            switch_threshold_psig=switch_threshold_psig,
        )
    finally:
        try:
            status = port.alicat.read_status()
            if status and status.barometric_pressure is not None:
                port.alicat.set_pressure(status.barometric_pressure)
                time.sleep(0.3)
        except Exception:
            pass
        port.alicat.cancel_hold()
        port.alicat.exhaust()
        time.sleep(2.0)
        port.alicat.disconnect()
        port.daq.cleanup()

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    output_file = output_dir / f"vacuum_correlation_{port_label}_{timestamp}.csv"
    _save_csv(
        readings,
        output_file,
        {
            "port": port_label,
            "target_psig": target_psig,
            "ramp_rate": ramp_rate,
            "sample_rate_hz": sample_rate_hz,
            "switch_threshold_psig": switch_threshold_psig,
        },
    )
    print(f"  Data saved to: {output_file}")
    _summarize(readings)


def main() -> int:
    parser = argparse.ArgumentParser(description="Vacuum correlation test")
    parser.add_argument("--port", choices=["port_a", "port_b"], default="port_a")
    parser.add_argument("--both-ports", action="store_true")
    parser.add_argument("--target-psig", type=float, default=-10.0)
    parser.add_argument("--ramp-rate", type=float, default=2.0)
    parser.add_argument("--sample-rate", type=float, default=5.0)
    parser.add_argument("--switch-threshold-psig", type=float, default=0.5)
    parser.add_argument("--output-dir", type=str, default="scripts/data")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    output_dir = PROJECT_ROOT / args.output_dir
    if args.both_ports:
        _run_for_port(
            "port_a",
            args.target_psig,
            args.ramp_rate,
            args.sample_rate,
            args.switch_threshold_psig,
            output_dir,
        )
        _run_for_port(
            "port_b",
            args.target_psig,
            args.ramp_rate,
            args.sample_rate,
            args.switch_threshold_psig,
            output_dir,
        )
    else:
        _run_for_port(
            args.port,
            args.target_psig,
            args.ramp_rate,
            args.sample_rate,
            args.switch_threshold_psig,
            output_dir,
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
