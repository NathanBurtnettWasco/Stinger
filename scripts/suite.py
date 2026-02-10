"""
Full test suite CLI: static, torr resolution, ramps, filter analysis, plotting.

Preferred suite entry point. See scripts/README.md for script layout.

Usage:
    python scripts/suite.py --ports port_a,port_b
    python scripts/suite.py --ports port_a --dry-run
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.lib.suite import run_suite


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
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
    ports = [p.strip() for p in args.ports.split(",") if p.strip()]
    return run_suite(
        ports=ports,
        output_root=args.output_root,
        run_id=args.run_id,
        dry_run=args.dry_run,
        skip_static=args.skip_static,
        skip_resolution=args.skip_resolution,
        skip_ramps=args.skip_ramps,
        include_ultra_slow=args.include_ultra_slow,
        only_filtering=args.only_filtering,
    )


if __name__ == "__main__":
    sys.exit(main())
