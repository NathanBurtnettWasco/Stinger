#!/usr/bin/env python3
"""Standalone preview entry point for the quality calibration UI."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from quality_cal.preview import main


if __name__ == '__main__':
    raise SystemExit(main())
