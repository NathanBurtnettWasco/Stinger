"""
Comprehensive Test Suite Runner - Run a full pressure-only test plan.

Usage:
    python run_comprehensive_suite.py --ports port_a,port_b
    python run_comprehensive_suite.py --ports port_a --dry-run
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import math
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, List, Sequence

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class RampPlan:
    start: float
    end: float
    rate: float
    settle: float
    label: str


@dataclass
class FilterCandidate:
    name: str
    kind: str
    param: float


def _run_command(cmd: List[str], dry_run: bool) -> tuple[int, str, str]:
    print("\n$ " + " ".join(cmd))
    if dry_run:
        return 0, "", ""
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.stdout:
        print(result.stdout)
    if result.returncode != 0 and result.stderr:
        print(result.stderr)
    return result.returncode, result.stdout, result.stderr


def _parse_saved_files(stdout: str) -> List[Path]:
    files = []
    for line in stdout.split("\n"):
        if "Data saved to:" in line:
            file_path = line.split("Data saved to:")[1].strip()
            files.append(Path(file_path))
    return files


def run_quick_static(port: str, duration: float, sample_rate: float, output_dir: Path, dry_run: bool) -> List[Path]:
    cmd = [
        sys.executable,
        "scripts/quick_static_test.py",
        "--port",
        port,
        "--duration",
        str(duration),
        "--sample-rate",
        str(sample_rate),
        "--no-filter",
        "--output-dir",
        str(output_dir),
    ]
    code, stdout, _ = _run_command(cmd, dry_run)
    return _parse_saved_files(stdout) if code == 0 else []


def run_torr_resolution(port: str, duration: float, sample_rate: float, alicat_rate: float, output_dir: Path, dry_run: bool) -> List[Path]:
    cmd = [
        sys.executable,
        "scripts/torr_resolution_test.py",
        "--port",
        port,
        "--duration",
        str(duration),
        "--sample-rate",
        str(sample_rate),
        "--alicat-rate",
        str(alicat_rate),
        "--output-dir",
        str(output_dir),
    ]
    code, stdout, _ = _run_command(cmd, dry_run)
    return _parse_saved_files(stdout) if code == 0 else []


def run_ramp(port: str, plan: RampPlan, output_dir: Path, dry_run: bool) -> List[Path]:
    cmd = [
        sys.executable,
        "scripts/ramp_test.py",
        "--port",
        port,
        "--start",
        str(plan.start),
        "--end",
        str(plan.end),
        "--rate",
        str(plan.rate),
        "--settle",
        str(plan.settle),
        "--output-dir",
        str(output_dir),
    ]
    code, stdout, _ = _run_command(cmd, dry_run)
    return _parse_saved_files(stdout) if code == 0 else []


def build_ramp_plan(include_ultra_slow: bool) -> List[RampPlan]:
    plans: List[RampPlan] = []

    dense_rates = [0.05, 0.1, 0.2]
    if include_ultra_slow:
        dense_rates = [0.01, 0.02] + dense_rates

    for rate in dense_rates:
        plans.append(RampPlan(15.0, 20.0, rate, 3.0, f"dense_low_up_{rate}"))
        plans.append(RampPlan(20.0, 15.0, rate, 3.0, f"dense_low_down_{rate}"))

    for rate in [0.5, 1.0, 2.0]:
        plans.append(RampPlan(15.0, 35.0, rate, 3.0, f"mid_up_{rate}"))
        plans.append(RampPlan(35.0, 15.0, rate, 3.0, f"mid_down_{rate}"))
        plans.append(RampPlan(35.0, 50.0, rate, 3.0, f"mid_high_up_{rate}"))

    for rate in [5.0, 10.0]:
        plans.append(RampPlan(15.0, 50.0, rate, 3.0, f"high_low_up_{rate}"))
        plans.append(RampPlan(50.0, 15.0, rate, 3.0, f"high_low_down_{rate}"))
        plans.append(RampPlan(50.0, 100.0, rate, 3.0, f"high_up_{rate}"))
        plans.append(RampPlan(100.0, 50.0, rate, 3.0, f"high_down_{rate}"))

    return plans


def _read_csv_rows(path: Path) -> tuple[List[str], List[List[str]]]:
    with path.open("r", newline="") as f:
        reader = csv.reader(f)
        rows = [row for row in reader if row]
    return rows[0], rows[1:]


def _read_ramp_csv(path: Path) -> dict[str, list]:
    with path.open("r", newline="") as f:
        reader = csv.reader(f)
        rows = []
        for row in reader:
            if not row:
                continue
            if row[0].startswith("#"):
                continue
            rows.append(row)
    header = rows[0]
    data_rows = rows[1:]
    idx = {name: i for i, name in enumerate(header)}

    def col(name: str) -> List[float]:
        return [float(r[idx[name]]) for r in data_rows]

    return {
        "elapsed_time": col("elapsed_time"),
        "phase": [r[idx["phase"]] for r in data_rows],
        "transducer_pressure": col("transducer_pressure_calc"),
        "alicat_pressure": col("alicat_pressure"),
    }


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


def _estimate_dt(time_values: Sequence[float]) -> float:
    if len(time_values) < 2:
        return 0.0
    diffs = np.diff(np.array(time_values))
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


def _collect_filter_metrics(
    static_files: Iterable[Path],
    ramp_files: Iterable[Path],
    candidates: List[FilterCandidate],
) -> List[dict[str, Any]]:
    results = []

    static_offsets = []
    for path in static_files:
        header, rows = _read_csv_rows(path)
        idx = {name: i for i, name in enumerate(header)}
        offsets = np.array([float(r[idx["offset_psi"]]) for r in rows])
        timestamps = [float(r[idx["timestamp"]]) for r in rows]
        static_offsets.append((offsets, _estimate_dt(timestamps)))

    ramp_data = []
    for path in ramp_files:
        data = _read_ramp_csv(path)
        phases = data["phase"]
        trans = np.array(data["transducer_pressure"])
        alicat = np.array(data["alicat_pressure"])
        elapsed = data["elapsed_time"]
        dt = _estimate_dt(elapsed)
        mask = np.array([p == "ramping" for p in phases])
        if mask.any():
            ramp_data.append((trans[mask], alicat[mask], dt))

    for candidate in candidates:
        noise_stds = []
        lag_seconds = []
        rmses = []

        for offsets, dt in static_offsets:
            if candidate.kind == "moving_average":
                window = max(1, int(candidate.param / dt)) if dt > 0 else 1
                filtered = _moving_average(offsets, window)
            else:
                filtered = _exp_smooth(offsets, candidate.param)
            noise_stds.append(float(np.std(filtered)))

        for trans, alicat, dt in ramp_data:
            if candidate.kind == "moving_average":
                window = max(1, int(candidate.param / dt)) if dt > 0 else 1
                filtered = _moving_average(trans, window)
            else:
                filtered = _exp_smooth(trans, candidate.param)
            lag_seconds.append(_best_lag_seconds(trans, filtered, dt))
            rmses.append(float(np.sqrt(np.mean((filtered - alicat) ** 2))))

        results.append(
            {
                "name": candidate.name,
                "kind": candidate.kind,
                "param": candidate.param,
                "static_noise_std": float(np.mean(noise_stds)) if noise_stds else math.nan,
                "ramp_lag_s": float(np.mean(lag_seconds)) if lag_seconds else math.nan,
                "ramp_rmse": float(np.mean(rmses)) if rmses else math.nan,
                "static_samples": len(static_offsets),
                "ramp_samples": len(ramp_data),
            }
        )

    return results


def run_filter_analysis(output_dir: Path, static_files: List[Path], ramp_files: List[Path], dry_run: bool) -> dict:
    if dry_run:
        return {"status": "skipped", "reason": "dry_run"}

    candidates = []
    for window_s in [0.05, 0.1, 0.2, 0.5, 1.0]:
        candidates.append(FilterCandidate(f"ma_{window_s}s", "moving_average", window_s))
    for alpha in [0.05, 0.1, 0.2, 0.3, 0.5]:
        candidates.append(FilterCandidate(f"exp_{alpha}", "exponential", alpha))

    rows = _collect_filter_metrics(static_files, ramp_files, candidates)
    if not rows:
        return {"status": "skipped", "reason": "no_data"}

    noise_min = min(float(r["static_noise_std"]) for r in rows if not math.isnan(float(r["static_noise_std"])) )
    lag_min = min(float(r["ramp_lag_s"]) for r in rows if not math.isnan(float(r["ramp_lag_s"])) )
    rmse_min = min(float(r["ramp_rmse"]) for r in rows if not math.isnan(float(r["ramp_rmse"])) )

    for row in rows:
        noise_score = float(row["static_noise_std"]) / noise_min if noise_min > 0 else math.inf
        lag_score = float(row["ramp_lag_s"]) / lag_min if lag_min > 0 else math.inf
        rmse_score = float(row["ramp_rmse"]) / rmse_min if rmse_min > 0 else math.inf
        row["score"] = 0.5 * noise_score + 0.3 * lag_score + 0.2 * rmse_score

    rows.sort(key=lambda r: r["score"])
    best = rows[0]

    analysis_dir = output_dir / "analysis"
    analysis_dir.mkdir(parents=True, exist_ok=True)

    report_path = analysis_dir / "filtering_report.csv"
    with report_path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "name",
            "kind",
            "param",
            "static_noise_std",
            "ramp_lag_s",
            "ramp_rmse",
            "score",
            "static_samples",
            "ramp_samples",
        ])
        for row in rows:
            writer.writerow([
                row["name"],
                row["kind"],
                row["param"],
                row["static_noise_std"],
                row["ramp_lag_s"],
                row["ramp_rmse"],
                row["score"],
                row["static_samples"],
                row["ramp_samples"],
            ])

    recommendation_path = analysis_dir / "filtering_recommendation.csv"
    with recommendation_path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["name", "kind", "param", "score"])
        writer.writerow([best["name"], best["kind"], best["param"], best["score"]])

    return {
        "status": "ok",
        "report": str(report_path),
        "recommendation": best,
    }


def run_plotting(output_dir: Path, dry_run: bool) -> None:
    cmd = [
        sys.executable,
        "scripts/plot_test_results.py",
        "--data-dir",
        str(output_dir),
    ]
    _run_command(cmd, dry_run)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run comprehensive pressure-only test suite")
    parser.add_argument("--ports", type=str, default="port_a,port_b", help="Comma-separated ports")
    parser.add_argument("--output-root", type=str, default="scripts/data", help="Root output directory")
    parser.add_argument("--run-id", type=str, default="", help="Optional run id suffix")
    parser.add_argument("--dry-run", action="store_true", help="Print commands without running")
    parser.add_argument("--skip-static", action="store_true", help="Skip static tests")
    parser.add_argument("--skip-resolution", action="store_true", help="Skip resolution tests")
    parser.add_argument("--skip-ramps", action="store_true", help="Skip ramp tests")
    parser.add_argument("--include-ultra-slow", action="store_true", help="Include 0.01-0.02 PSI/s ramps")
    parser.add_argument("--only-filtering", action="store_true", help="Run calibration + filtering only")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    ports = [p.strip() for p in args.ports.split(",") if p.strip()]
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    run_suffix = f"_{args.run_id}" if args.run_id else ""
    output_dir = Path(args.output_root) / f"run_{timestamp}{run_suffix}"
    output_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "run_id": output_dir.name,
        "ports": ports,
        "output_dir": str(output_dir),
        "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "dry_run": args.dry_run,
        "tests": [],
        "filtering": None,
    }

    print("\n" + "=" * 70)
    print("COMPREHENSIVE TEST SUITE")
    print("=" * 70)
    print(f"Ports: {', '.join(ports)}")
    print(f"Output dir: {output_dir}")
    print("=" * 70)

    calibration_static: List[Path] = []
    calibration_ramps: List[Path] = []

    for port in ports:
        print(f"\n>>> Calibration: {port}")
        if not args.skip_static:
            files = run_quick_static(port, duration=30.0, sample_rate=50.0, output_dir=output_dir, dry_run=args.dry_run)
            calibration_static.extend(files)
            manifest["tests"].append({"type": "static_calibration", "port": port, "files": [str(f) for f in files]})

        if not args.skip_ramps:
            for plan in [
                RampPlan(15.0, 30.0, 1.0, 3.0, "calibration_mid"),
                RampPlan(30.0, 50.0, 5.0, 3.0, "calibration_high"),
            ]:
                files = run_ramp(port, plan, output_dir, args.dry_run)
                calibration_ramps.extend(files)
                manifest["tests"].append({
                    "type": "ramp_calibration",
                    "port": port,
                    "plan": plan.__dict__,
                    "files": [str(f) for f in files],
                })

    manifest["filtering"] = run_filter_analysis(output_dir, calibration_static, calibration_ramps, args.dry_run)

    if args.only_filtering:
        manifest["ended_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        manifest_path = output_dir / "run_manifest.json"
        with manifest_path.open("w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)
        print("\nFiltering-only run complete.")
        print("Run manifest saved to:")
        print(f"  {manifest_path}")
        return 0

    for port in ports:
        print(f"\n>>> Main suite: {port}")
        if not args.skip_static:
            files = run_quick_static(port, duration=30.0, sample_rate=50.0, output_dir=output_dir, dry_run=args.dry_run)
            manifest["tests"].append({"type": "static", "port": port, "files": [str(f) for f in files]})

        if not args.skip_resolution:
            files = run_torr_resolution(
                port,
                duration=30.0,
                sample_rate=50.0,
                alicat_rate=10.0,
                output_dir=output_dir,
                dry_run=args.dry_run,
            )
            manifest["tests"].append({"type": "resolution", "port": port, "files": [str(f) for f in files]})

        if not args.skip_ramps:
            for plan in build_ramp_plan(args.include_ultra_slow):
                files = run_ramp(port, plan, output_dir, args.dry_run)
                manifest["tests"].append({
                    "type": "ramp",
                    "port": port,
                    "plan": plan.__dict__,
                    "files": [str(f) for f in files],
                })

    run_plotting(output_dir, args.dry_run)

    manifest["ended_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    manifest_path = output_dir / "run_manifest.json"
    with manifest_path.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    print("\nRun manifest saved to:")
    print(f"  {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
