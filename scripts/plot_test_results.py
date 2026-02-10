"""
Plot summary graphs for Stinger test data.

Usage:
    python scripts/plot_test_results.py --data-dir scripts/data/20260203
"""

from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import matplotlib.pyplot as plt
import numpy as np
from matplotlib import tri

TORR_PER_PSI = 51.715


def load_filter_recommendation(data_dir: Path) -> Optional[Dict[str, float | str]]:
    rec_path = data_dir / "analysis" / "filtering_recommendation.csv"
    if not rec_path.exists():
        return None
    header, rows = read_csv_rows(rec_path)
    if not rows:
        return None
    idx = {name: i for i, name in enumerate(header)}
    return {
        "name": rows[0][idx["name"]],
        "kind": rows[0][idx["kind"]],
        "param": float(rows[0][idx["param"]]),
    }


def _estimate_dt(values: List[float]) -> float:
    if len(values) < 2:
        return 0.0
    diffs = np.diff(np.array(values))
    diffs = diffs[diffs > 0]
    return float(np.median(diffs)) if diffs.size else 0.0


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


def apply_filter(values: List[float], dt: float, filter_cfg: Optional[Dict[str, float | str]]) -> Optional[np.ndarray]:
    if not filter_cfg or not values:
        return None
    series = np.array(values)
    kind = str(filter_cfg.get("kind"))
    param = float(filter_cfg.get("param", 0.0))
    if kind == "moving_average":
        window = max(1, int(param / dt)) if dt > 0 else 1
        return _moving_average(series, window)
    if kind == "exponential":
        return _exp_smooth(series, param)
    return None


def read_csv_rows(path: Path) -> Tuple[List[str], List[List[str]]]:
    with path.open("r", newline="") as f:
        reader = csv.reader(f)
        rows = [row for row in reader if row]
    return rows[0], rows[1:]


def read_ramp_csv(path: Path) -> Dict[str, List[float]]:
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
        "timestamp": col("timestamp"),
        "elapsed_time": col("elapsed_time"),
        "phase": [r[idx["phase"]] for r in data_rows],
        "transducer_pressure": col("transducer_pressure_calc"),
        "alicat_pressure": col("alicat_pressure"),
        "offset": col("offset_calc"),
        "rate": col("ramp_rate_commanded"),
    }


def read_grid_summary(path: Path) -> Tuple[List[str], List[List[str]]]:
    with path.open("r", newline="") as f:
        reader = csv.reader(f)
        rows = []
        for row in reader:
            if not row:
                continue
            if row[0].startswith("#"):
                continue
            rows.append(row)
    if not rows:
        return [], []
    return rows[0], rows[1:]


def plot_static(port: str, path: Path, out_dir: Path) -> None:
    header, rows = read_csv_rows(path)
    idx = {name: i for i, name in enumerate(header)}
    offsets = [float(r[idx["offset_psi"]]) for r in rows]
    times = [float(r[idx["timestamp"]]) for r in rows]
    t0 = times[0]
    elapsed = [t - t0 for t in times]

    plt.figure(figsize=(10, 4))
    plt.plot(elapsed, offsets, lw=0.8)
    plt.title(f"{port} Static Offset vs Time")
    plt.xlabel("Time (s)")
    plt.ylabel("Offset (PSI)")
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(out_dir / f"{port}_static_offset_time.png", dpi=160)
    plt.close()

    plt.figure(figsize=(6, 4))
    plt.hist(offsets, bins=40, color="#4C78A8")
    plt.title(f"{port} Static Offset Histogram")
    plt.xlabel("Offset (PSI)")
    plt.ylabel("Count")
    plt.tight_layout()
    plt.savefig(out_dir / f"{port}_static_offset_hist.png", dpi=160)
    plt.close()


def plot_resolution(port: str, path: Path, out_dir: Path) -> None:
    header, rows = read_csv_rows(path)
    idx = {name: i for i, name in enumerate(header)}
    times = [float(r[idx["timestamp"]]) for r in rows]
    t0 = times[0]
    elapsed = [t - t0 for t in times]
    trans_torr = [float(r[idx["transducer_pressure_torr"]]) for r in rows]
    alicat_raw = [float(r[idx["alicat_pressure_raw"]]) for r in rows]
    alicat_units = rows[0][idx["alicat_units"]]
    if alicat_units.upper().startswith("P"):
        alicat_torr = [v * TORR_PER_PSI for v in alicat_raw]
    else:
        alicat_torr = alicat_raw

    plt.figure(figsize=(10, 4))
    plt.plot(elapsed, trans_torr, label="Transducer", lw=0.8)
    plt.plot(elapsed, alicat_torr, label="Alicat", lw=0.8)
    plt.title(f"{port} Torr Resolution Time Series")
    plt.xlabel("Time (s)")
    plt.ylabel("Pressure (Torr)")
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(out_dir / f"{port}_resolution_time.png", dpi=160)
    plt.close()


def plot_ramp(port: str, path: Path, out_dir: Path) -> Tuple[float, float]:
    data = read_ramp_csv(path)
    elapsed = data["elapsed_time"]
    trans = data["transducer_pressure"]
    alicat = data["alicat_pressure"]
    offset = data["offset"]
    rate = data["rate"]
    ramp_rate = float(np.median([r for r in rate if r > 0])) if any(r > 0 for r in rate) else 0.0

    plt.figure(figsize=(10, 4))
    plt.plot(elapsed, alicat, label="Alicat", lw=0.8)
    plt.plot(elapsed, trans, label="Transducer", lw=0.8)
    plt.title(f"{port} Ramp Pressure vs Time ({path.name})")
    plt.xlabel("Time (s)")
    plt.ylabel("Pressure (PSI)")
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(out_dir / f"{path.stem}_pressure.png", dpi=160)
    plt.close()

    plt.figure(figsize=(10, 4))
    plt.plot(elapsed, offset, lw=0.8)
    plt.title(f"{port} Ramp Offset vs Time ({path.name})")
    plt.xlabel("Time (s)")
    plt.ylabel("Offset (PSI)")
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(out_dir / f"{path.stem}_offset.png", dpi=160)
    plt.close()

    phases = data["phase"]
    ramp_offsets = [o for o, p in zip(offset, phases) if p == "ramping"]
    mean_offset = float(np.mean(ramp_offsets)) if ramp_offsets else math.nan
    return ramp_rate, mean_offset


def summarize_ramp_file(
    port: str,
    path: Path,
    filter_cfg: Optional[Dict[str, float | str]] = None,
) -> Dict[str, float | str | int]:
    data = read_ramp_csv(path)
    phases = data["phase"]
    alicat = data["alicat_pressure"]
    offsets = data["offset"]
    elapsed = data["elapsed_time"]
    rates = data["rate"]

    ramp_offsets = [o for o, p in zip(offsets, phases) if p == "ramping"]
    ramp_start = [p for p, ph in zip(alicat, phases) if ph == "start"]
    ramp_end = [p for p, ph in zip(alicat, phases) if ph == "settled"]
    ramp_times = [t for t, ph in zip(elapsed, phases) if ph == "ramping"]

    ramp_rate = float(np.median([r for r in rates if r > 0])) if any(r > 0 for r in rates) else 0.0
    start_pressure = float(np.median(ramp_start)) if ramp_start else float("nan")
    end_pressure = float(np.median(ramp_end)) if ramp_end else float("nan")
    direction = "up" if end_pressure > start_pressure else "down"
    ramp_duration = (max(ramp_times) - min(ramp_times)) if ramp_times else 0.0

    filtered_std = math.nan
    filtered_mean = math.nan
    if ramp_offsets:
        dt = _estimate_dt(ramp_times)
        filtered = apply_filter(ramp_offsets, dt, filter_cfg)
        if filtered is not None:
            filtered_mean = float(np.mean(filtered))
            filtered_std = float(np.std(filtered))

    return {
        "port": port,
        "source_file": path.name,
        "ramp_rate_psi_s": ramp_rate,
        "start_pressure_psia": start_pressure,
        "end_pressure_psia": end_pressure,
        "direction": direction,
        "ramp_offset_mean_psi": float(np.mean(ramp_offsets)) if ramp_offsets else math.nan,
        "ramp_offset_std_psi": float(np.std(ramp_offsets)) if ramp_offsets else math.nan,
        "ramp_offset_mean_filtered_psi": filtered_mean,
        "ramp_offset_std_filtered_psi": filtered_std,
        "ramp_samples": len(ramp_offsets),
        "ramp_duration_s": ramp_duration,
    }


def summarize_static_file(
    port: str,
    path: Path,
    filter_cfg: Optional[Dict[str, float | str]] = None,
) -> Dict[str, float | str | int]:
    header, rows = read_csv_rows(path)
    idx = {name: i for i, name in enumerate(header)}
    offsets = [float(r[idx["offset_psi"]]) for r in rows]
    timestamps = [float(r[idx["timestamp"]]) for r in rows]
    dt = _estimate_dt(timestamps)
    filtered = apply_filter(offsets, dt, filter_cfg)
    filtered_std = float(np.std(filtered)) if filtered is not None else math.nan
    return {
        "port": port,
        "source_file": path.name,
        "offset_mean_psi": float(np.mean(offsets)) if offsets else math.nan,
        "offset_std_psi": float(np.std(offsets)) if offsets else math.nan,
        "offset_std_filtered_psi": filtered_std,
        "samples": len(offsets),
    }


def summarize_resolution_file(port: str, path: Path) -> Dict[str, float | str | int]:
    header, rows = read_csv_rows(path)
    idx = {name: i for i, name in enumerate(header)}
    alicat_raw = [float(r[idx["alicat_pressure_raw"]]) for r in rows]
    offsets = [float(r[idx["offset_torr"]]) for r in rows]
    units = rows[0][idx["alicat_units"]] if rows else ""
    if units.upper().startswith("P"):
        alicat_torr = [v * TORR_PER_PSI for v in alicat_raw]
    else:
        alicat_torr = alicat_raw

    valid = []
    for a, o in zip(alicat_torr, offsets):
        if a <= 0.0:
            continue
        if abs(o) > 5000:
            continue
        valid.append(o)

    return {
        "port": port,
        "source_file": path.name,
        "offset_mean_torr": float(np.mean(valid)) if valid else math.nan,
        "offset_std_torr": float(np.std(valid)) if valid else math.nan,
        "samples": len(offsets),
        "valid_samples": len(valid),
    }


def _aggregate_grid_points(rows: List[List[str]], idx: Dict[str, int]) -> List[Dict[str, float]]:
    buckets: Dict[tuple[float, float], List[Dict[str, float]]] = {}
    for row in rows:
        rate = float(row[idx["rate_psi_s"]])
        pressure = float(row[idx["target_pressure_psia"]])
        key = (round(rate, 4), round(pressure, 4))
        bucket = buckets.setdefault(key, [])
        bucket.append({
            "rate": rate,
            "pressure": pressure,
            "ramp_offset": float(row[idx["ramp_mean_offset_psi"]]),
            "hold_offset": float(row[idx["hold_mean_offset_psi"]]),
        })

    points = []
    for (rate, pressure), items in buckets.items():
        ramp_vals = [i["ramp_offset"] for i in items if not math.isnan(i["ramp_offset"])]
        hold_vals = [i["hold_offset"] for i in items if not math.isnan(i["hold_offset"])]
        points.append({
            "rate": rate,
            "pressure": pressure,
            "ramp_offset": float(np.mean(ramp_vals)) if ramp_vals else float("nan"),
            "hold_offset": float(np.mean(hold_vals)) if hold_vals else float("nan"),
        })

    return points


def _try_grid_mesh(points: List[Dict[str, float]], z_key: str) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    rates = sorted(set(p["rate"] for p in points))
    pressures = sorted(set(p["pressure"] for p in points))
    if len(points) != len(rates) * len(pressures):
        return np.array([]), np.array([]), np.array([])

    grid = np.full((len(pressures), len(rates)), np.nan)
    index = {(p["pressure"], p["rate"]): p for p in points}
    for i, pressure in enumerate(pressures):
        for j, rate in enumerate(rates):
            value = index[(pressure, rate)].get(z_key, float("nan"))
            grid[i, j] = value

    return np.array(rates), np.array(pressures), grid


def plot_grid_surfaces(port: str, points: List[Dict[str, float]], out_dir: Path) -> None:
    if not points:
        return

    for z_key, label in (
        ("ramp_offset", "Ramp Mean Offset"),
        ("hold_offset", "Hold Mean Offset"),
    ):
        x = np.array([p["rate"] for p in points])
        y = np.array([p["pressure"] for p in points])
        z = np.array([p[z_key] for p in points])

        if len(x) < 3:
            continue

        triang = tri.Triangulation(x, y)

        fig = plt.figure(figsize=(8, 6))
        ax = fig.add_subplot(111, projection="3d")
        surf = ax.plot_trisurf(triang, z, cmap="viridis", linewidth=0.2, antialiased=True)
        ax.set_title(f"{port} {label} Surface")
        ax.set_xlabel("Ramp Rate (PSI/s)")
        ax.set_ylabel("Pressure (PSIA)")
        ax.set_zlabel("Offset (PSI)")
        fig.colorbar(surf, shrink=0.65, aspect=12)
        fig.tight_layout()
        fig.savefig(out_dir / f"{port}_{z_key}_surface_3d.png", dpi=160)
        plt.close(fig)

        fig = plt.figure(figsize=(7, 5))
        ax = fig.add_subplot(111, projection="3d")
        scatter = ax.scatter(x, y, z, c=z, cmap="viridis", s=20)
        ax.set_title(f"{port} {label} Scatter")
        ax.set_xlabel("Ramp Rate (PSI/s)")
        ax.set_ylabel("Pressure (PSIA)")
        ax.set_zlabel("Offset (PSI)")
        fig.colorbar(scatter, shrink=0.7, aspect=12)
        fig.tight_layout()
        fig.savefig(out_dir / f"{port}_{z_key}_scatter_3d.png", dpi=160)
        plt.close(fig)

        plt.figure(figsize=(7, 5))
        contour = plt.tricontourf(triang, z, levels=14, cmap="viridis")
        plt.title(f"{port} {label} Contour")
        plt.xlabel("Ramp Rate (PSI/s)")
        plt.ylabel("Pressure (PSIA)")
        plt.colorbar(contour)
        plt.tight_layout()
        plt.savefig(out_dir / f"{port}_{z_key}_contour.png", dpi=160)
        plt.close()

        grid_rates, grid_pressures, grid = _try_grid_mesh(points, z_key)
        if grid.size:
            plt.figure(figsize=(7, 5))
            mesh = plt.pcolormesh(grid_rates, grid_pressures, grid, shading="auto", cmap="viridis")
            plt.title(f"{port} {label} Heatmap")
            plt.xlabel("Ramp Rate (PSI/s)")
            plt.ylabel("Pressure (PSIA)")
            plt.colorbar(mesh)
            plt.tight_layout()
            plt.savefig(out_dir / f"{port}_{z_key}_heatmap.png", dpi=160)
            plt.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Plot Stinger test results")
    parser.add_argument("--data-dir", type=str, required=True, help="Data directory")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    if not data_dir.exists():
        raise SystemExit(f"Data dir not found: {data_dir}")

    plot_root = data_dir / "plots"
    plot_root.mkdir(parents=True, exist_ok=True)

    ports = {"port_a": [], "port_b": []}

    for csv_path in sorted(data_dir.glob("*.csv")):
        name = csv_path.name
        if "port_a" in name:
            ports["port_a"].append(csv_path)
        if "port_b" in name:
            ports["port_b"].append(csv_path)

    summary_rows = []
    grid_summary_rows = []
    grid_summary_path = None
    ramp_detail_rows = []
    static_rows = []
    resolution_rows = []
    inventory_rows = []
    filter_cfg = load_filter_recommendation(data_dir)

    for port, files in ports.items():
        out_dir = plot_root / port
        out_dir.mkdir(parents=True, exist_ok=True)

        ramp_points = []
        grid_points = []
        for path in files:
            if path.name.startswith("quick_static"):
                plot_static(port, path, out_dir)
                static_rows.append(summarize_static_file(port, path, filter_cfg))
                inventory_rows.append([port, "quick_static", path.name, path.stat().st_size])
            elif path.name.startswith("torr_resolution"):
                plot_resolution(port, path, out_dir)
                resolution_rows.append(summarize_resolution_file(port, path))
                inventory_rows.append([port, "torr_resolution", path.name, path.stat().st_size])
            elif path.name.startswith("ramp_"):
                rate, mean_offset = plot_ramp(port, path, out_dir)
                if not math.isnan(mean_offset):
                    ramp_points.append((rate, mean_offset, path.name))
                ramp_detail_rows.append(summarize_ramp_file(port, path, filter_cfg))
                inventory_rows.append([port, "ramp", path.name, path.stat().st_size])
            elif path.name.startswith("grid_summary_"):
                header, rows = read_grid_summary(path)
                if header and rows:
                    idx = {name: i for i, name in enumerate(header)}
                    grid_points.extend(_aggregate_grid_points(rows, idx))
                    for row in rows:
                        grid_summary_rows.append([port, path.name] + row)
                inventory_rows.append([port, "grid_summary", path.name, path.stat().st_size])

        if ramp_points:
            ramp_points.sort(key=lambda x: x[0])
            rates = [p[0] for p in ramp_points]
            offsets = [p[1] for p in ramp_points]

            plt.figure(figsize=(7, 4))
            plt.plot(rates, offsets, marker="o")
            plt.title(f"{port} Mean Ramp Offset vs Rate")
            plt.xlabel("Ramp Rate (PSI/s)")
            plt.ylabel("Mean Offset (PSI)")
            plt.grid(True, alpha=0.3)
            plt.tight_layout()
            plt.savefig(out_dir / f"{port}_offset_vs_rate.png", dpi=160)
            plt.close()

            for rate, mean_offset, name in ramp_points:
                summary_rows.append([port, rate, mean_offset, name])

        if grid_points:
            plot_grid_surfaces(port, grid_points, out_dir)

    summary_path = plot_root / "ramp_offset_summary.csv"
    with summary_path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["port", "rate_psi_s", "mean_offset_psi", "source_file"])
        writer.writerows(summary_rows)

    if grid_summary_rows:
        grid_summary_path = plot_root / "grid_offset_summary.csv"
        with grid_summary_path.open("w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "port",
                "source_file",
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
            ])
            writer.writerows(grid_summary_rows)

    print(f"Plots saved to: {plot_root}")
    print(f"Summary CSV: {summary_path}")
    if grid_summary_path:
        print(f"Grid summary CSV: {grid_summary_path}")

    analysis_root = data_dir / "analysis"
    analysis_root.mkdir(parents=True, exist_ok=True)

    if ramp_detail_rows:
        ramp_detail_path = analysis_root / "ramp_summary_detailed.csv"
        with ramp_detail_path.open("w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    "port",
                    "source_file",
                    "ramp_rate_psi_s",
                    "start_pressure_psia",
                    "end_pressure_psia",
                    "direction",
                    "ramp_offset_mean_psi",
                    "ramp_offset_std_psi",
                    "ramp_offset_mean_filtered_psi",
                    "ramp_offset_std_filtered_psi",
                    "ramp_samples",
                    "ramp_duration_s",
                ]
            )
            for row in ramp_detail_rows:
                writer.writerow(
                    [
                        row["port"],
                        row["source_file"],
                        row["ramp_rate_psi_s"],
                        row["start_pressure_psia"],
                        row["end_pressure_psia"],
                        row["direction"],
                        row["ramp_offset_mean_psi"],
                        row["ramp_offset_std_psi"],
                        row["ramp_offset_mean_filtered_psi"],
                        row["ramp_offset_std_filtered_psi"],
                        row["ramp_samples"],
                        row["ramp_duration_s"],
                    ]
                )

        agg = {}
        for row in ramp_detail_rows:
            key = (row["port"], row["ramp_rate_psi_s"], row["direction"])
            agg.setdefault(key, []).append(row["ramp_offset_mean_psi"])

        ramp_agg_path = analysis_root / "ramp_summary_agg.csv"
        with ramp_agg_path.open("w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    "port",
                    "ramp_rate_psi_s",
                    "direction",
                    "mean_offset_psi",
                    "std_offset_psi",
                    "runs",
                ]
            )
            for (port, rate, direction), offsets in sorted(agg.items()):
                writer.writerow(
                    [
                        port,
                        rate,
                        direction,
                        float(np.mean(offsets)),
                        float(np.std(offsets)) if len(offsets) > 1 else 0.0,
                        len(offsets),
                    ]
                )

    if static_rows:
        static_path = analysis_root / "static_summary.csv"
        with static_path.open("w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "port",
                "source_file",
                "offset_mean_psi",
                "offset_std_psi",
                "offset_std_filtered_psi",
                "samples",
            ])
            for row in static_rows:
                writer.writerow(
                    [
                        row["port"],
                        row["source_file"],
                        row["offset_mean_psi"],
                        row["offset_std_psi"],
                        row["offset_std_filtered_psi"],
                        row["samples"],
                    ]
                )

    if resolution_rows:
        resolution_path = analysis_root / "resolution_summary.csv"
        with resolution_path.open("w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    "port",
                    "source_file",
                    "offset_mean_torr",
                    "offset_std_torr",
                    "samples",
                    "valid_samples",
                ]
            )
            for row in resolution_rows:
                writer.writerow(
                    [
                        row["port"],
                        row["source_file"],
                        row["offset_mean_torr"],
                        row["offset_std_torr"],
                        row["samples"],
                        row["valid_samples"],
                    ]
                )

    if inventory_rows:
        inventory_path = analysis_root / "data_inventory.csv"
        with inventory_path.open("w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["port", "type", "source_file", "file_size_bytes"])
            writer.writerows(inventory_rows)

    print(f"Analysis CSVs: {analysis_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
