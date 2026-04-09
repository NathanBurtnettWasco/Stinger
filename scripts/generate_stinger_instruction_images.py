#!/usr/bin/env python3
"""CLI entry point for deterministic Stinger work-instruction image generation."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts._stinger_instruction_images import build_arg_parser, generate_instruction_images


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    exports, review_path = generate_instruction_images(
        workflow=args.workflow,
        output_dir=Path(args.output_dir),
        variant=args.variant,
        scene_id=args.scene,
        review_sheet=args.review_sheet,
    )

    print(f'Created {args.workflow.upper()} instruction images:')
    for record in exports:
        print(f' - [{record.variant}] {record.path}')
    if review_path is not None:
        print(f' - [review-sheet] {review_path}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
