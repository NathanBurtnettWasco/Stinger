from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime

from app.database import operations


class _FakeQuery:
    def __init__(self, rows):
        self._rows = rows

    def filter_by(self, **_kwargs):
        return self

    def all(self):
        return self._rows


class _FakeSession:
    def __init__(self, rows):
        self._rows = rows

    def query(self, _model):
        return _FakeQuery(self._rows)


class _FakeOrder:
    def __init__(self, part_id: str, cal_date: datetime, start_time: datetime):
        self.ShopOrder = 'WO-100'
        self.PartID = part_id
        self.LastSequenceCalibrated = '0042'
        self.OrderQTY = 25
        self.OperatorID = 'OP1'
        self.EquipmentID = 'EQ1'
        self.CalibrationDate = cal_date
        self.StartTime = start_time


def test_validate_shop_order_uses_latest_when_duplicates_exist(monkeypatch, caplog) -> None:
    older = _FakeOrder('PART-OLD', datetime(2025, 1, 1), datetime(2025, 1, 1, 7, 0, 0))
    newer = _FakeOrder('PART-NEW', datetime(2025, 1, 2), datetime(2025, 1, 2, 7, 0, 0))
    fake_session = _FakeSession([older, newer])

    @contextmanager
    def _fake_scope():
        yield fake_session

    monkeypatch.setattr(operations, 'session_scope', _fake_scope)

    with caplog.at_level('WARNING'):
        result = operations.validate_shop_order('WO-100')

    assert result is not None
    assert result['PartID'] == 'PART-NEW'
    assert 'returned 2 rows' in caplog.text
