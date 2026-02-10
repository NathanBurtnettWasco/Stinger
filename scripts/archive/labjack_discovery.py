"""
LabJack discovery + basic read checks.

Usage (from repo root):
    python scripts/labjack_discovery.py
    python scripts/labjack_discovery.py --port port_a
    python scripts/labjack_discovery.py --connection USB --identifier ANY
    python scripts/labjack_discovery.py --toggle-solenoid
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import load_config

logger = logging.getLogger(__name__)

try:
    from labjack import ljm
    LJM_AVAILABLE = True
except ImportError:
    LJM_AVAILABLE = False


def _ip_to_string(ip_value: Any) -> Optional[str]:
    if not LJM_AVAILABLE:
        return None
    try:
        return ljm.numberToIP(ip_value)
    except Exception:
        return None


def _try_list_all() -> Tuple[int, List[Any], List[Any], List[Any], List[Any]]:
    if not LJM_AVAILABLE:
        return 0, [], [], [], []

    dt_any = getattr(ljm.constants, 'dtANY', -1)
    ct_any = getattr(ljm.constants, 'ctANY', -1)

    list_all_attempts: Iterable[Tuple[str, Tuple[Any, ...]]] = (
        ('listAll', (dt_any, ct_any)),
        ('listAll', (dt_any,)),
        ('listAllS', ('ANY', 'ANY')),
        ('listAllS', ('T7', 'ANY')),
    )

    last_error: Optional[Exception] = None
    for func_name, args in list_all_attempts:
        list_func = getattr(ljm, func_name, None)
        if list_func is None:
            continue
        try:
            result = list_func(*args)
            if len(result) >= 5:
                return (
                    int(result[0]),
                    list(result[1]),
                    list(result[2]),
                    list(result[3]),
                    list(result[4]),
                )
        except Exception as exc:
            last_error = exc

    if last_error is not None:
        logger.warning('LJM listAll failed: %s', last_error)
    return 0, [], [], [], []


def _format_device_row(
    device_type: Any,
    connection_type: Any,
    serial_number: Any,
    ip_value: Any,
) -> str:
    ip_str = _ip_to_string(ip_value)
    ip_display = ip_str if ip_str else str(ip_value)
    return f'device_type={device_type}, connection={connection_type}, serial={serial_number}, ip={ip_display}'


def discover_devices() -> None:
    num_found, device_types, connection_types, serial_numbers, ip_addresses = _try_list_all()
    logger.info('LJM discovery: %s device(s) found', num_found)

    for idx in range(num_found):
        logger.info(
            'LJM device %s: %s',
            idx + 1,
            _format_device_row(
                device_types[idx],
                connection_types[idx],
                serial_numbers[idx],
                ip_addresses[idx],
            ),
        )


def build_labjack_config(config: Dict[str, Any], port_key: str) -> Dict[str, Any]:
    labjack_config = config.get('hardware', {}).get('labjack', {})
    base = {
        'device_type': labjack_config.get('device_type', 'T7'),
        'connection_type': labjack_config.get('connection_type', 'USB'),
        'identifier': labjack_config.get('identifier', 'ANY'),
    }
    return {**base, **labjack_config.get(port_key, {})}


def open_handle(device_type: str, connection_type: str, identifier: str) -> Optional[int]:
    if not LJM_AVAILABLE:
        return None
    try:
        return ljm.openS(device_type, connection_type, identifier)
    except Exception as exc:
        logger.error('LJM open failed (%s/%s/%s): %s', device_type, connection_type, identifier, exc)
        return None


def log_handle_info(handle: int) -> None:
    if not LJM_AVAILABLE:
        return
    try:
        info = ljm.getHandleInfo(handle)
    except Exception as exc:
        logger.warning('LJM getHandleInfo failed: %s', exc)
        return

    if len(info) >= 6:
        device_type, connection_type, serial_number, ip_value, port, _ = info[:6]
        ip_str = _ip_to_string(ip_value)
        logger.info(
            'LJM handle info: device_type=%s, connection=%s, serial=%s, ip=%s, port=%s',
            device_type,
            connection_type,
            serial_number,
            ip_str if ip_str else ip_value,
            port,
        )


def read_port_signals(handle: int, port_config: Dict[str, Any]) -> None:
    transducer_ain = port_config.get('transducer_ain')
    switch_no_dio = port_config.get('switch_no_dio')
    switch_nc_dio = port_config.get('switch_nc_dio')
    solenoid_dio = port_config.get('solenoid_dio')

    if transducer_ain is not None:
        try:
            voltage = ljm.eReadName(handle, f'AIN{transducer_ain}')
            logger.info('AIN%s voltage: %s V', transducer_ain, voltage)
        except Exception as exc:
            logger.error('AIN read failed: %s', exc)

    if switch_no_dio is not None and switch_nc_dio is not None:
        try:
            states = ljm.eReadNames(handle, 2, [f'DIO{switch_no_dio}', f'DIO{switch_nc_dio}'])
            logger.info('DIO%s (NO)=%s, DIO%s (NC)=%s', switch_no_dio, states[0], switch_nc_dio, states[1])
        except Exception as exc:
            logger.error('DIO read failed: %s', exc)

    if solenoid_dio is not None:
        logger.info('Configured solenoid DIO%s', solenoid_dio)


def toggle_solenoid(handle: int, solenoid_dio: Optional[int]) -> None:
    if solenoid_dio is None:
        return
    try:
        logger.info('Solenoid DIO%s -> vacuum', solenoid_dio)
        ljm.eWriteName(handle, f'DIO{solenoid_dio}', 1)
        logger.info('Solenoid DIO%s -> atmosphere', solenoid_dio)
        ljm.eWriteName(handle, f'DIO{solenoid_dio}', 0)
    except Exception as exc:
        logger.error('Solenoid toggle failed: %s', exc)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

    parser = argparse.ArgumentParser(description='LabJack discovery + basic read checks')
    parser.add_argument('--port', default='port_a', choices=['port_a', 'port_b'])
    parser.add_argument('--device-type', dest='device_type', default=None)
    parser.add_argument('--connection', dest='connection_type', default=None)
    parser.add_argument('--identifier', default=None)
    parser.add_argument('--toggle-solenoid', action='store_true')
    args = parser.parse_args()

    if not LJM_AVAILABLE:
        logger.error('labjack.ljm not installed or not available in this environment.')
        return

    discover_devices()

    config = load_config()
    port_config = build_labjack_config(config, args.port)

    device_type = args.device_type or port_config.get('device_type', 'T7')
    connection_type = args.connection_type or port_config.get('connection_type', 'USB')
    identifier = args.identifier or port_config.get('identifier', 'ANY')

    handle = open_handle(device_type, connection_type, identifier)
    if handle is None:
        return

    try:
        log_handle_info(handle)
        read_port_signals(handle, port_config)
        if args.toggle_solenoid:
            toggle_solenoid(handle, port_config.get('solenoid_dio'))
    finally:
        try:
            ljm.close(handle)
        except Exception as exc:
            logger.warning('LJM close failed: %s', exc)


if __name__ == '__main__':
    main()
