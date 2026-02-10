"""Shared protocol types for test execution events and failures."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TestFailureCode(str, Enum):
    ROUTE_FAILURE = 'route_failure'
    TARGET_TIMEOUT = 'target_timeout'
    ATMOSPHERE_TIMEOUT = 'atmosphere_timeout'
    EDGE_NOT_FOUND = 'edge_not_found'
    NO_SWITCH_DETECTED = 'no_switch_detected'
    RAMP_RATE_FAILURE = 'ramp_rate_failure'
    PRESSURE_COMMAND_FAILURE = 'pressure_command_failure'
    CANCELLED = 'cancelled'
    INTERNAL_ERROR = 'internal_error'


class TestFailure(RuntimeError):
    def __init__(self, code: TestFailureCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    def __str__(self) -> str:
        return f'{self.code.value}: {self.message}'


@dataclass(frozen=True)
class TestEvent:
    event_type: str
    port_id: str
    data: dict[str, Any] = field(default_factory=dict)
