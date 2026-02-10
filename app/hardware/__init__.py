"""
Hardware abstraction layer.

Provides interfaces for:
- LabJack T-series - analog input, digital I/O
- Alicat pressure controllers
- Port abstraction combining LabJack + Alicat
"""

from .labjack import LabJackController
from .alicat import AlicatController
from .port import Port, PortManager

__all__ = ['LabJackController', 'AlicatController', 'Port', 'PortManager']
