"""Unit tests for parsing typed control config."""

from __future__ import annotations

import pytest

from app.services.control_config import ControlConfigError, parse_control_config


def test_parse_control_config_defaults() -> None:
    parsed = parse_control_config({})
    assert parsed.ramps.precision_sweep_rate_torr_per_sec == 5.0
    assert parsed.ramps.precision_edge_rate_torr_per_sec == 5.0
    assert parsed.cycling.num_cycles == 3
    assert parsed.debounce.stable_sample_count == 3


def test_parse_control_config_rejects_unknown_keys() -> None:
    with pytest.raises(ControlConfigError, match='Unknown keys in control.control'):
        parse_control_config({'control': {'unexpected': 1}})


def test_parse_control_config_rejects_non_mapping_sections() -> None:
    with pytest.raises(ControlConfigError, match='control section must be a mapping'):
        parse_control_config({'control': 'bad'})

    with pytest.raises(ControlConfigError, match='control subsections must be mappings'):
        parse_control_config({'control': {'ramps': [], 'cycling': {}, 'edge_detection': {}, 'debounce': {}}})
