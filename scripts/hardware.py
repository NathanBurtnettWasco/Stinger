"""
Hardware diagnostics CLI: discover, switch, switch-sweep, solenoids, alicat-dual.

Preferred diagnostics entry point. See scripts/README.md for script layout.

Usage:
    python scripts/hardware.py discover [--port port_a]
    python scripts/hardware.py switch --port port_a --com-dio 3
    python scripts/hardware.py switch-sweep --port port_a --com-dio 3 --start 15 --end 50
    python scripts/hardware.py solenoids
    python scripts/hardware.py alicat-dual [--com-port COM9]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.lib.hardware import (
    run_alicat_dual,
    run_discover,
    run_solenoids,
    run_switch,
    run_switch_sweep,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Hardware diagnostics: discovery, switch, solenoids, Alicat")
    subparsers = parser.add_subparsers(dest="command", required=True)

    discover_parser = subparsers.add_parser("discover", help="LabJack discovery and basic read")
    discover_parser.add_argument("--connection", default=None)
    discover_parser.add_argument("--identifier", default=None)
    discover_parser.add_argument("--port", default=None)
    discover_parser.add_argument("--toggle-solenoid", action="store_true")
    discover_parser.set_defaults(func=lambda a: run_discover(
        connection=a.connection, identifier=a.identifier, port=a.port, toggle_solenoid=a.toggle_solenoid
    ))

    switch_parser = subparsers.add_parser("switch", help="Pressure switch NO/NC/COM test")
    switch_parser.add_argument("--port", default="port_a")
    switch_parser.add_argument("--com-dio", type=int, required=True, help="DIO for COM pin")
    switch_parser.add_argument("--no-dio", type=int, default=None)
    switch_parser.add_argument("--nc-dio", type=int, default=None)
    switch_parser.add_argument("--samples", type=int, default=20)
    switch_parser.add_argument("--interval", type=float, default=0.1)
    switch_parser.set_defaults(func=lambda a: run_switch(
        port=a.port, com_dio=a.com_dio, no_dio=a.no_dio, nc_dio=a.nc_dio,
        samples=a.samples, interval=a.interval
    ))

    sweep_parser = subparsers.add_parser("switch-sweep", help="Pressure switch sweep test")
    sweep_parser.add_argument("--port", default="port_a")
    sweep_parser.add_argument("--com-dio", type=int, required=True)
    sweep_parser.add_argument("--no-dio", type=int, default=None)
    sweep_parser.add_argument("--nc-dio", type=int, default=None)
    sweep_parser.add_argument("--start", type=float, default=15.0)
    sweep_parser.add_argument("--end", type=float, default=50.0)
    sweep_parser.add_argument("--rate", type=float, default=1.0)
    sweep_parser.add_argument("--settle", type=float, default=3.0)
    sweep_parser.add_argument("--hold", type=float, default=3.0)
    sweep_parser.add_argument("--output-dir", default="scripts/data")
    sweep_parser.add_argument("--com-high", action="store_true")
    sweep_parser.set_defaults(func=lambda a: run_switch_sweep(
        port=a.port, com_dio=a.com_dio, no_dio=a.no_dio, nc_dio=a.nc_dio,
        start=a.start, end=a.end, rate=a.rate, settle=a.settle, hold=a.hold,
        output_dir=a.output_dir, com_high=a.com_high
    ))

    solenoids_parser = subparsers.add_parser("solenoids", help="Solenoid toggle test")
    solenoids_parser.set_defaults(func=lambda a: run_solenoids())

    alicat_parser = subparsers.add_parser("alicat-dual", help="Dual Alicat test on shared COM")
    alicat_parser.add_argument("--com-port", default=None)
    alicat_parser.add_argument("--addr-a", default=None)
    alicat_parser.add_argument("--addr-b", default=None)
    alicat_parser.add_argument("--baudrate", type=int, default=None)
    alicat_parser.add_argument("--timeout", type=float, default=None)
    alicat_parser.add_argument("--setpoint-delta", type=float, default=0.5)
    alicat_parser.add_argument("--settle-s", type=float, default=0.5)
    alicat_parser.add_argument("--skip-modes", action="store_true")
    alicat_parser.add_argument("--set-psi", action="store_true")
    alicat_parser.add_argument("--no-restore", action="store_true")
    alicat_parser.set_defaults(func=lambda a: run_alicat_dual(
        com_port=a.com_port, addr_a=a.addr_a, addr_b=a.addr_b,
        baudrate=a.baudrate, timeout=a.timeout,
        setpoint_delta=a.setpoint_delta, settle_s=a.settle_s,
        skip_modes=a.skip_modes, set_psi=a.set_psi, no_restore=a.no_restore
    ))

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
