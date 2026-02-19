"""Compatibility entrypoint for archived pressure switch sweep script."""

from __future__ import annotations

import runpy
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    archived = root / 'scripts' / 'archive' / 'pressure_switch_sweep_test.py'
    if not archived.exists():
        raise FileNotFoundError(f'Archived sweep script not found: {archived}')

    # Execute archived script as __main__ while preserving CLI args.
    runpy.run_path(str(archived), run_name='__main__')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
