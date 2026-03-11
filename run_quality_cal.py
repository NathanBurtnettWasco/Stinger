#!/usr/bin/env python3
"""Standalone entry point for the quality calibration application."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from quality_cal.main import main


if __name__ == "__main__":
    sys.exit(main())
