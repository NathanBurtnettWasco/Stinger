"""Replay switch streams to validate deterministic edge detection."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from app.services.sweep_primitives import DebounceState, observe_debounced_transition


def main() -> int:
    parser = argparse.ArgumentParser(description='Replay edge detector over CSV data')
    parser.add_argument('input_csv', type=Path)
    parser.add_argument('--state-column', default='switch_activated')
    parser.add_argument('--pressure-column', default='alicat_pressure')
    parser.add_argument('--stable-count', type=int, default=3)
    parser.add_argument('--min-edge-ms', type=float, default=50.0)
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

        now_s = idx * 0.02
        state, committed = observe_debounced_transition(
            state,
            current,
            args.stable_count,
            args.min_edge_ms / 1000.0,
            now_s,
            track_last_sample=True,
            update_edge_time_on_reject=True,
        )
        if committed is None:
            continue
        edge_count += 1
        pressure = row.get(args.pressure_column, '')
        print(f'edge#{edge_count}: state={committed} pressure={pressure} sample={idx}')

    print(f'total_edges={edge_count}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
