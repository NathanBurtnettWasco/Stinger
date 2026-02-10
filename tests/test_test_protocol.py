"""Unit tests for test execution protocol types."""

from app.services.test_protocol import TestEvent, TestFailure, TestFailureCode


def test_test_failure_string_includes_code_and_message() -> None:
    err = TestFailure(TestFailureCode.TARGET_TIMEOUT, 'timed out waiting for target')
    assert err.code == TestFailureCode.TARGET_TIMEOUT
    assert str(err) == 'target_timeout: timed out waiting for target'


def test_test_event_defaults_data_to_empty_mapping() -> None:
    event = TestEvent(event_type='progress', port_id='port_a')
    assert event.data == {}
