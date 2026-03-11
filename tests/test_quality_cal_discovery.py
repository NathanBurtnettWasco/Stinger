from quality_cal.core.hardware_discovery import build_candidate_ports


def test_build_candidate_ports_preserves_order_and_dedupes():
    ports = build_candidate_ports(
        ["COM9", "COM10"],
        ["COM10", "COM11"],
        ["COM11", "COM12", ""],
    )

    assert ports == ["COM9", "COM10", "COM11", "COM12"]
