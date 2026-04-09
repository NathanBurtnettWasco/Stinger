#!/usr/bin/env python3
"""Legacy wrapper for QAL 15 setup screenshots."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts._stinger_instruction_images import generate_legacy_qal15_setup_images


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description='Create QAL 15 setup screenshots for the work instruction.',
    )
    parser.add_argument(
        '--output-dir',
        default=str(ROOT / 'docs' / 'generated' / 'qal15'),
        help='Directory to write the PNG files into.',
    )
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    created = generate_legacy_qal15_setup_images(Path(args.output_dir))
    print('Created QAL 15 setup images:')
    for path in created:
        print(f' - {path}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
