from quality_cal.core.leak_check_runner import compute_leak_rate_psi_per_min


def test_compute_leak_rate_returns_positive_decay_rate():
    samples = [
        (0.0, 100.0),
        (30.0, 99.9),
        (60.0, 99.8),
        (90.0, 99.7),
    ]

    rate = compute_leak_rate_psi_per_min(samples)

    assert rate is not None
    assert round(rate, 4) == 0.2


def test_compute_leak_rate_clamps_negative_decay():
    samples = [
        (0.0, 100.0),
        (60.0, 100.1),
    ]

    rate = compute_leak_rate_psi_per_min(samples)

    assert rate == 0.0
