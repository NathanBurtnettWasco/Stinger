"""Replay switch streams to validate deterministic edge detection."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.services.sweep_primitives import DebounceState, observe_debounced_transition


def main() -> int:
    parser = argparse.ArgumentParser(description='Replay edge detector over CSV data')
    parser.add_argument('input_csv', type=Path)
    parser.add_argument('--state-column', default='switch_activated')
    parser.add_argument('--pressure-column', default='alicat_pressure')
    parser.add_argument('--stable-count', type=int, default=3)
    parser.add_argument('--min-edge-ms', type=float, default=50.0)
    parser.add_argument('--sample-interval-s', type=float, default=0.02)
    parser.add_argument(
        '--invert-state',
        action='store_true',
        help='Invert parsed state (useful for active-low switch channels)',
    )
    args = parser.parse_args()

    rows = list(csv.DictReader(args.input_csv.open('r', newline='')))
    state = DebounceState()
    edge_count = 0

    for idx, row in enumerate(rows):
        raw = str(row.get(args.state_column, '')).strip().lower()
        if raw in {'1', 'true', 'yes'}:
            current = True
        elif raw in {'0', 'false', 'no'}:
            current = False
        else:
            continue
        if args.invert_state:
            current = not current

        now_s = idx * args.sample_interval_s
        pressure_val = row.get(args.pressure_column, '')
        try:
            pressure = float(pressure_val)
        except (TypeError, ValueError):
            pressure = None

        state, committed, committed_pressure = observe_debounced_transition(
            state,
            current,
            args.stable_count,
            args.min_edge_ms / 1000.0,
            now_s,
            track_last_sample=True,
            update_edge_time_on_reject=True,
            current_pressure=pressure,
        )
        if committed is None:
            continue
        edge_count += 1
        edge_pressure = committed_pressure if committed_pressure is not None else pressure_val
        print(f'edge#{edge_count}: state={committed} pressure={edge_pressure} sample={idx}')

    print(f'total_edges={edge_count}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
