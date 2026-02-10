"""
Measure max command-response AIN read rate for LabJack T7-Pro.

Usage (from repo root):
    python scripts/labjack_ain_rate_test.py --ain 0 --seconds 3
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import load_config

logger = logging.getLogger(__name__)

try:
    from labjack import ljm
    LJM_AVAILABLE = True
except ImportError:
    LJM_AVAILABLE = False


def open_handle(device_type: str, connection_type: str, identifier: str) -> Optional[int]:
    if not LJM_AVAILABLE:
        return None
    try:
        return ljm.openS(device_type, connection_type, identifier)
    except Exception as exc:
        logger.error('LJM open failed (%s/%s/%s): %s', device_type, connection_type, identifier, exc)
        return None


def measure_rate(handle: int, ain: int, seconds: float) -> float:
    end_time = time.perf_counter() + seconds
    reads = 0
    errors = 0
    last_value = None
    while time.perf_counter() < end_time:
        try:
            last_value = ljm.eReadName(handle, f'AIN{ain}')
            reads += 1
        except Exception:
            errors += 1
    elapsed = seconds
    rate = reads / elapsed if elapsed > 0 else 0.0
    logger.info('AIN%s last=%.6f V reads=%s errors=%s rate=%.1f Hz', ain, last_value, reads, errors, rate)
    return rate


def main() -> None:
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

    parser = argparse.ArgumentParser(description='LabJack AIN rate test')
    parser.add_argument('--ain', type=int, default=0)
    parser.add_argument('--seconds', type=float, default=3.0)
    args = parser.parse_args()

    if not LJM_AVAILABLE:
        logger.error('labjack.ljm not installed or not available in this environment.')
        return

    config = load_config()
    labjack_config = config.get('hardware', {}).get('labjack', {})
    device_type = labjack_config.get('device_type', 'T7')
    connection_type = labjack_config.get('connection_type', 'USB')
    identifier = labjack_config.get('identifier', 'ANY')

    handle = open_handle(device_type, connection_type, identifier)
    if handle is None:
        return

    try:
        logger.info('Measuring max command-response AIN rate...')
        measure_rate(handle, args.ain, args.seconds)
    finally:
        try:
            ljm.close(handle)
        except Exception as exc:
            logger.warning('LJM close failed: %s', exc)


if __name__ == '__main__':
    main()
