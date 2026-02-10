"""
Read all Stinger-assigned LabJack DIO lines.

Usage (from repo root):
    python scripts/labjack_dio_scan.py
    python scripts/labjack_dio_scan.py --connection USB --identifier ANY
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import load_config

logger = logging.getLogger(__name__)

try:
    from labjack import ljm
    LJM_AVAILABLE = True
except ImportError:
    LJM_AVAILABLE = False


PORT_A_DB9 = {
    1: 0,
    2: 1,
    3: 2,
    4: 3,
    5: 4,
    6: 5,
    7: 6,
    8: 7,
    9: 8,
}

PORT_B_DB9 = {
    1: 9,
    2: 10,
    3: 11,
    4: 12,
    5: 13,
    6: 14,
    7: 15,
    8: 16,
    9: 17,
}

RELAY_DIO = {
    'port_a_relay': 18,
    'port_b_relay': 19,
}


def build_labjack_config(config: Dict[str, Any]) -> Dict[str, Any]:
    labjack_config = config.get('hardware', {}).get('labjack', {})
    return {
        'device_type': labjack_config.get('device_type', 'T7'),
        'connection_type': labjack_config.get('connection_type', 'USB'),
        'identifier': labjack_config.get('identifier', 'ANY'),
    }


def open_handle(device_type: str, connection_type: str, identifier: str) -> Optional[int]:
    if not LJM_AVAILABLE:
        return None
    try:
        return ljm.openS(device_type, connection_type, identifier)
    except Exception as exc:
        logger.error('LJM open failed (%s/%s/%s): %s', device_type, connection_type, identifier, exc)
        return None


def read_dio_values(handle: int, dio_list: List[int]) -> Dict[int, float]:
    names = [f'DIO{dio}' for dio in dio_list]
    values = ljm.eReadNames(handle, len(names), names)
    return dict(zip(dio_list, values))


def log_group(title: str, mapping: Dict[Any, int], values: Dict[int, float]) -> None:
    logger.info('%s', title)
    for pin, dio in mapping.items():
        value = values.get(dio)
        logger.info('  pin %s -> DIO%s = %s', pin, dio, value)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

    parser = argparse.ArgumentParser(description='LabJack DIO scan (Stinger mapping)')
    parser.add_argument('--device-type', dest='device_type', default=None)
    parser.add_argument('--connection', dest='connection_type', default=None)
    parser.add_argument('--identifier', default=None)
    args = parser.parse_args()

    if not LJM_AVAILABLE:
        logger.error('labjack.ljm not installed or not available in this environment.')
        return

    config = load_config()
    base = build_labjack_config(config)

    device_type = args.device_type or base['device_type']
    connection_type = args.connection_type or base['connection_type']
    identifier = args.identifier or base['identifier']

    handle = open_handle(device_type, connection_type, identifier)
    if handle is None:
        return

    try:
        dio_list = list(range(0, 20))
        values = read_dio_values(handle, dio_list)
        log_group('Port A DB9', PORT_A_DB9, values)
        log_group('Port B DB9', PORT_B_DB9, values)
        log_group('Relays', RELAY_DIO, values)
    finally:
        try:
            ljm.close(handle)
        except Exception as exc:
            logger.warning('LJM close failed: %s', exc)


if __name__ == '__main__':
    main()
