"""Optional hardware-in-the-loop checks for LabJack wiring and I/O."""

from __future__ import annotations

import os

import pytest

from tests.labjack_smoke_check import run_check

pytestmark = pytest.mark.hardware

if os.getenv('STINGER_RUN_HARDWARE_TESTS', '').lower() not in {'1', 'true', 'yes'}:
    pytest.skip(
        'hardware tests are opt-in; set STINGER_RUN_HARDWARE_TESTS=1 to run',
        allow_module_level=True,
    )


def test_port_a_labjack_smoke_check() -> None:
    run_check('port_a', toggle_solenoid=False)


def test_port_b_labjack_smoke_check() -> None:
    run_check('port_b', toggle_solenoid=False)
