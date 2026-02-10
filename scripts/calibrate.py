"""
Calibration workflow CLI: collect correlation data and/or analyze CSVs.

Usage:
    python scripts/calibrate.py collect --port port_a
    python scripts/calibrate.py collect --both-ports [--auto-start]
    python scripts/calibrate.py analyze scripts/data/comprehensive_correlation_port_a_*.csv
    python scripts/calibrate.py full --both-ports [--auto-start]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure project root is on path so app and scripts are importable
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.lib.calibration import run_analyze, run_collect


def _cmd_collect(args: argparse.Namespace) -> int:
    ports = ["port_a", "port_b"] if args.both_ports else [args.port or "port_a"]
    saved = run_collect(
        ports=ports,
        sample_rate=args.sample_rate,
        output_dir=args.output_dir,
        auto_start=args.auto_start,
    )
    if not saved:
        print("No data saved (all ports failed).")
        return 1
    print("\nSaved file(s):")
    for p in saved:
        print(f"  {p}")
    if len(saved) > 1:
        print("\nTo analyze: python scripts/calibrate.py analyze " + " ".join(f'"{p}"' for p in saved))
    else:
        print(f"\nTo analyze: python scripts/calibrate.py analyze {saved[0]}")
    return 0


def _cmd_analyze(args: argparse.Namespace) -> int:
    paths = [Path(p) for p in args.csv_files]
    for p in paths:
        if not p.exists():
            print(f"File not found: {p}")
            return 1
    return run_analyze(csv_paths=paths, no_plots=args.no_plots)


def _cmd_full(args: argparse.Namespace) -> int:
    ports = ["port_a", "port_b"] if args.both_ports else [args.port or "port_a"]
    saved = run_collect(
        ports=ports,
        sample_rate=args.sample_rate,
        output_dir=args.output_dir,
        auto_start=args.auto_start,
    )
    if not saved:
        return 1
    return run_analyze(csv_paths=saved, no_plots=args.no_plots)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Calibration: collect transducer-Alicat correlation data and/or analyze."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    collect_parser = subparsers.add_parser("collect", help="Run correlation test (raw data)")
    collect_parser.add_argument("--port", default=None, help="Single port (e.g. port_a)")
    collect_parser.add_argument("--both-ports", action="store_true", help="Run on port_a then port_b")
    collect_parser.add_argument("--sample-rate", type=float, default=50.0)
    collect_parser.add_argument("--output-dir", default="scripts/data")
    collect_parser.add_argument("--auto-start", action="store_true", help="Skip start prompt")
    collect_parser.set_defaults(func=_cmd_collect)

    analyze_parser = subparsers.add_parser("analyze", help="Analyze one or more correlation CSVs")
    analyze_parser.add_argument("csv_files", nargs="+", help="Paths to comprehensive_correlation_*.csv")
    analyze_parser.add_argument("--no-plots", action="store_true", help="Skip plots")
    analyze_parser.set_defaults(func=_cmd_analyze)

    full_parser = subparsers.add_parser("full", help="Collect then analyze (both ports)")
    full_parser.add_argument("--port", default=None)
    full_parser.add_argument("--both-ports", action="store_true")
    full_parser.add_argument("--sample-rate", type=float, default=50.0)
    full_parser.add_argument("--output-dir", default="scripts/data")
    full_parser.add_argument("--auto-start", action="store_true")
    full_parser.add_argument("--no-plots", action="store_true")
    full_parser.set_defaults(func=_cmd_full)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
