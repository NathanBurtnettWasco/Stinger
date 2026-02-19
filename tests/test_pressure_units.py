"""Legacy umbrella module kept for compatibility after test split."""

import pytest

pytest.skip(
    'Pressure unit coverage moved to test_pressure_conversion.py, test_executor_pressure.py, and test_alicat_commands.py',
    allow_module_level=True,
)
