# Testing Guide

This repository separates fast unit tests from optional hardware-in-the-loop checks.

## Unit Tests (Default)

Run the default suite:

```powershell
python -m pytest
```

Pytest is configured to skip hardware-marked tests by default via `pytest.ini`.

## Coverage Reporting

Run tests with module coverage:

```powershell
python -m pytest --cov=app --cov-report=term-missing --cov-report=xml
```

The XML report is written to `coverage.xml`.

Latest baseline snapshot is tracked in `docs/COVERAGE_BASELINE.md`.

## Hardware Integration Tests (Opt-In)

Hardware-in-the-loop tests are marked with `@pytest.mark.hardware` and require explicit opt-in.

Enable and run:

```powershell
$env:STINGER_RUN_HARDWARE_TESTS = "1"
python -m pytest -m hardware -o addopts="" tests/test_hardware_integration.py
```

These tests call the LabJack smoke workflow and require configured, connected hardware.
