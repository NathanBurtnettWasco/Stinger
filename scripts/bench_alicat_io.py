#!/usr/bin/env python3
"""
Benchmark Alicat serial I/O throughput and latency on real hardware.

Usage examples:
  python scripts/bench_alicat_io.py --port COM9 --baud 115200 --addresses A B
  python scripts/bench_alicat_io.py --port COM9 --baud 115200 --addresses B --allow-control
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any

# Ensure repo root is on sys.path when running from scripts/
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.hardware.alicat import AlicatController  # noqa: E402


def _stats(samples_s: list[float]) -> dict[str, Any]:
    if not samples_s:
        return {}
    ordered = sorted(samples_s)

    def pct(p: float) -> float:
        idx = int((len(ordered) - 1) * p)
        return ordered[idx]

    return {
        "n": len(ordered),
        "min_ms": round(ordered[0] * 1000.0, 3),
        "mean_ms": round(statistics.mean(ordered) * 1000.0, 3),
        "median_ms": round(statistics.median(ordered) * 1000.0, 3),
        "p95_ms": round(pct(0.95) * 1000.0, 3),
        "max_ms": round(ordered[-1] * 1000.0, 3),
    }


def _hz_from_mean_ms(stats_dict: dict[str, Any]) -> float | None:
    mean_ms = stats_dict.get("mean_ms")
    if not mean_ms:
        return None
    return round(1000.0 / float(mean_ms), 2)


def _build_controller(
    port: str,
    baud: int,
    timeout_s: float,
    address: str,
    auto_configure: bool,
    units_code: int,
) -> AlicatController:
    cfg = {
        "com_port": port,
        "baudrate": baud,
        "timeout_s": timeout_s,
        "address": address,
        "auto_tare_on_connect": False,
        "auto_configure": auto_configure,
        "pressure_units_stat": 2,
        "pressure_units_value": units_code,
        "pressure_units_group": 0,
        "pressure_units_override": 0,
        "pressure_index": 0,
        "gauge_index": 1,
        "barometric_index": 2,
        "setpoint_index": 3,
    }
    return AlicatController(cfg)


def _read_bench(controller: AlicatController, n: int, warmup: int) -> dict[str, Any]:
    for _ in range(warmup):
        controller.read_status()
    samples: list[float] = []
    ok = 0
    for _ in range(n):
        t0 = time.perf_counter()
        reading = controller.read_status()
        samples.append(time.perf_counter() - t0)
        if reading is not None:
            ok += 1
    result = _stats(samples)
    result["success_count"] = ok
    result["fail_count"] = n - ok
    result["effective_hz_mean"] = _hz_from_mean_ms(result)
    return result


def _pair_read_bench(
    first: AlicatController,
    second: AlicatController,
    n: int,
    warmup: int,
) -> dict[str, Any]:
    for _ in range(warmup):
        first.read_status()
        second.read_status()
    samples: list[float] = []
    for _ in range(n):
        t0 = time.perf_counter()
        first.read_status()
        second.read_status()
        samples.append(time.perf_counter() - t0)
    result = _stats(samples)
    hz = _hz_from_mean_ms(result)
    result["effective_pair_hz_mean"] = hz
    result["effective_per_device_hz_mean"] = hz
    return result


def _safe_control_bench(
    controller: AlicatController,
    n: int,
    ramp_psi_s: float,
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    baseline = controller.read_status()
    if baseline is None:
        out["error"] = "No baseline read; skipped control benchmark."
        return out

    target_psi = float(baseline.setpoint)
    set_samples: list[float] = []
    for _ in range(n):
        t0 = time.perf_counter()
        controller.set_pressure(target_psi)
        set_samples.append(time.perf_counter() - t0)
    out["set_pressure_same_setpoint"] = _stats(set_samples)
    out["set_pressure_same_setpoint"]["target_psi"] = round(target_psi, 6)
    out["set_pressure_same_setpoint"]["effective_hz_mean"] = _hz_from_mean_ms(
        out["set_pressure_same_setpoint"]
    )

    ramp_samples: list[float] = []
    for _ in range(n):
        t0 = time.perf_counter()
        controller.set_ramp_rate(ramp_psi_s)
        ramp_samples.append(time.perf_counter() - t0)
    out["set_ramp_rate"] = _stats(ramp_samples)
    out["set_ramp_rate"]["ramp_psi_per_s"] = ramp_psi_s
    out["set_ramp_rate"]["effective_hz_mean"] = _hz_from_mean_ms(out["set_ramp_rate"])
    return out


def _target_assessment(
    single_read_hz: dict[str, float | None],
    pair_hz: float | None,
) -> dict[str, Any]:
    return {
        "single_device_50hz_feasible": any((hz or 0.0) >= 50.0 for hz in single_read_hz.values()),
        "single_device_100hz_feasible": any((hz or 0.0) >= 100.0 for hz in single_read_hz.values()),
        "dual_shared_port_50hz_per_device_feasible": (pair_hz or 0.0) >= 50.0,
        "dual_shared_port_100hz_per_device_feasible": (pair_hz or 0.0) >= 100.0,
        "note": (
            "Dual shared-port per-device Hz is limited by combined cycle time "
            "(query A + query B on the same serial link)."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark Alicat serial performance.")
    parser.add_argument("--port", default="COM9")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--timeout-s", type=float, default=0.05)
    parser.add_argument("--addresses", nargs="+", default=["A", "B"])
    parser.add_argument("--units-code", type=int, default=10, help="Alicat DCU pressure unit code.")
    parser.add_argument("--samples-read", type=int, default=250)
    parser.add_argument("--samples-control", type=int, default=80)
    parser.add_argument("--warmup", type=int, default=10)
    parser.add_argument("--ramp-psi-s", type=float, default=100.0)
    parser.add_argument(
        "--allow-control",
        action="store_true",
        help="Also benchmark safe control commands (same setpoint + fixed ramp).",
    )
    parser.add_argument(
        "--skip-auto-configure",
        action="store_true",
        help="Disable Alicat auto-configuration (usually leave off).",
    )
    args = parser.parse_args()

    addresses = [a.strip().upper() for a in args.addresses if a.strip()]
    if not addresses:
        print("No valid addresses provided.", file=sys.stderr)
        return 2

    controllers: dict[str, AlicatController] = {}
    report: dict[str, Any] = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "config": {
            "port": args.port,
            "baud": args.baud,
            "timeout_s": args.timeout_s,
            "addresses": addresses,
            "units_code": args.units_code,
            "samples_read": args.samples_read,
            "samples_control": args.samples_control,
            "warmup": args.warmup,
            "allow_control": args.allow_control,
        },
        "connect": {},
        "read_bench": {},
        "control_bench": {},
        "assessment": {},
    }

    try:
        # Connect each configured address.
        for address in addresses:
            c = _build_controller(
                port=args.port,
                baud=args.baud,
                timeout_s=args.timeout_s,
                address=address,
                auto_configure=not args.skip_auto_configure,
                units_code=args.units_code,
            )
            t0 = time.perf_counter()
            ok = c.connect()
            report["connect"][address] = {
                "ok": ok,
                "connect_ms": round((time.perf_counter() - t0) * 1000.0, 3),
            }
            if ok:
                controllers[address] = c
            else:
                c.disconnect()

        if not controllers:
            report["error"] = "No controllers connected."
            print(json.dumps(report, indent=2))
            return 2

        # Per-device read benchmark.
        single_hz: dict[str, float | None] = {}
        for address, controller in controllers.items():
            rb = _read_bench(controller, n=args.samples_read, warmup=args.warmup)
            report["read_bench"][f"read_status_{address}"] = rb
            single_hz[address] = rb.get("effective_hz_mean")

        # Shared-port pair benchmark if at least two addresses are connected.
        pair_hz: float | None = None
        if len(controllers) >= 2:
            addrs = list(controllers.keys())[:2]
            pair = _pair_read_bench(
                controllers[addrs[0]],
                controllers[addrs[1]],
                n=args.samples_read,
                warmup=max(2, args.warmup // 2),
            )
            report["read_bench"][f"pair_cycle_{addrs[0]}_then_{addrs[1]}"] = pair
            pair_hz = pair.get("effective_per_device_hz_mean")

        if args.allow_control:
            # Safe control benchmark on first connected address only.
            first_addr = next(iter(controllers))
            report["control_bench"][first_addr] = _safe_control_bench(
                controllers[first_addr],
                n=args.samples_control,
                ramp_psi_s=args.ramp_psi_s,
            )

        report["assessment"] = _target_assessment(single_read_hz=single_hz, pair_hz=pair_hz)
        print(json.dumps(report, indent=2))
        return 0
    finally:
        for controller in controllers.values():
            try:
                controller.disconnect()
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
