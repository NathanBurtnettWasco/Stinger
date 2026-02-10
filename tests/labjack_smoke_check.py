"""
Manual LabJack smoke check.

Usage (from repo root):
    python tests/labjack_smoke_check.py
    python tests/labjack_smoke_check.py --port port_a
    python tests/labjack_smoke_check.py --toggle-solenoid
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Any, Dict

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import load_config
from app.hardware.labjack import LabJackController

logger = logging.getLogger(__name__)


def build_labjack_config(config: Dict[str, Any], port_key: str) -> Dict[str, Any]:
    labjack_config = config.get('hardware', {}).get('labjack', {})
    base = {
        'device_type': labjack_config.get('device_type', 'T7'),
        'connection_type': labjack_config.get('connection_type', 'USB'),
        'identifier': labjack_config.get('identifier', 'ANY'),
    }
    return {**base, **labjack_config.get(port_key, {})}


def run_check(port_key: str, toggle_solenoid: bool) -> None:
    config = load_config()
    port_config = build_labjack_config(config, port_key)

    controller = LabJackController(port_config)
    if not controller.configure():
        raise RuntimeError(f"LabJack configure failed for {port_key}")

    reading = controller.read_transducer()
    switch_state = controller.read_switch_state()

    logger.info("%s transducer: %s", port_key, reading)
    logger.info("%s switch: %s", port_key, switch_state)

    if toggle_solenoid:
        logger.info("%s solenoid -> vacuum", port_key)
        controller.set_solenoid(True)
        logger.info("%s solenoid -> atmosphere", port_key)
        controller.set_solenoid(False)

    controller.cleanup()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

    parser = argparse.ArgumentParser(description='LabJack smoke check')
    parser.add_argument('--port', default='port_a', choices=['port_a', 'port_b'])
    parser.add_argument('--toggle-solenoid', action='store_true')
    args = parser.parse_args()

    run_check(args.port, args.toggle_solenoid)


if __name__ == '__main__':
    main()
