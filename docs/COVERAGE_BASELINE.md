# Coverage Baseline

Baseline captured on 2026-02-10 with:

```powershell
python -m pytest --cov=app --cov-report=term-missing --cov-report=xml
```

Result summary:

- Tests: `62 passed, 1 skipped`
- Total line coverage (`app/`): `28%` (`6977` statements, `5022` missed)

Higher coverage areas:

- `app/services/control_config.py`: `100%`
- `app/services/test_protocol.py`: `100%`
- `app/services/state/port_state_machine.py`: `89%`
- `app/services/sweep_utils.py`: `93%`
- `app/hardware/port.py`: `73%`
- `app/services/test_executor.py`: `69%`

Lower coverage areas (priority opportunities):

- `app/services/work_order_controller.py`: `11%`
- `app/database/operations.py`: `14%`
- `app/database/session.py`: `29%`
- `app/hardware/alicat.py`: `39%`
- `app/hardware/labjack.py`: `35%`
- UI modules under `app/ui/`: largely `0%`

Notes:

- Hardware integration tests are intentionally excluded from the default run.
- Coverage XML is generated at `coverage.xml` for tooling integration.
