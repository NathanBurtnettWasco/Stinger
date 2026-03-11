"""Configuration loader for the standalone quality calibration app."""

from __future__ import annotations

import logging
import logging.handlers
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import yaml

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class QualitySettings:
    pressure_points_psia: list[float]
    pressure_tolerance_psia: float
    settle_tolerance_psia: float
    settle_hold_s: float
    settle_timeout_s: float
    static_hold_s: float
    sample_hz: float
    leak_check_target_psia: float
    leak_check_duration_s: float
    leak_check_sample_hz: float
    leak_check_max_rate_psi_per_min: Optional[float]
    leak_check_ramp_rate_psi_per_s: float
    report_output_dir: Path
    report_template_path: Path
    report_filename_prefix: str


def get_default_config_path() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "quality_cal_config.yaml"
    return Path(__file__).resolve().parent.parent / "quality_cal_config.yaml"


def load_config(config_path: Optional[Path] = None) -> dict[str, Any]:
    path = config_path or get_default_config_path()
    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found: {path}")

    with open(path, "r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle)

    if not isinstance(config, dict):
        raise ValueError("Configuration root must be a mapping")

    validate_config(config)
    return config


def validate_config(config: dict[str, Any]) -> None:
    required = ["app", "hardware", "quality", "logging"]
    for section in required:
        if section not in config:
            raise ValueError(f"Missing required config section: {section}")

    hardware = config.get("hardware", {})
    if "labjack" not in hardware or "alicat" not in hardware:
        raise ValueError('Config "hardware" must define both "labjack" and "alicat"')

    quality_cfg = config.get("quality", {})
    points = build_pressure_points(quality_cfg)
    if not points:
        raise ValueError("quality configuration must define at least one pressure point")


def build_pressure_points(quality_cfg: dict[str, Any]) -> list[float]:
    explicit_points = quality_cfg.get("pressure_points_psia")
    if isinstance(explicit_points, list) and explicit_points:
        points = [_coerce_float(value) for value in explicit_points]
        return _normalize_points(points)

    schedule_cfg = quality_cfg.get("pressure_schedule", {}) or {}
    max_psia = _coerce_float(schedule_cfg.get("max_psia", 115.0))
    dense_up_to = _coerce_float(schedule_cfg.get("dense_up_to_psia", 30.0))
    dense_step = _coerce_float(schedule_cfg.get("dense_step_psia", 1.0))
    medium_up_to = _coerce_float(schedule_cfg.get("medium_up_to_psia", 60.0))
    medium_step = _coerce_float(schedule_cfg.get("medium_step_psia", 2.0))
    high_step = _coerce_float(schedule_cfg.get("high_step_psia", 5.0))
    start_psia = _coerce_float(schedule_cfg.get("start_psia", 1.0))

    points: list[float] = []
    points.extend(_build_range(start_psia, dense_up_to, dense_step))
    points.extend(_build_range(dense_up_to + medium_step, medium_up_to, medium_step))
    points.extend(_build_range(medium_up_to + high_step, max_psia, high_step))
    if max_psia not in points:
        points.append(max_psia)
    return _normalize_points(points)


def parse_quality_settings(config: dict[str, Any]) -> QualitySettings:
    quality_cfg = config.get("quality", {})
    report_cfg = quality_cfg.get("report", {}) or {}
    leak_cfg = quality_cfg.get("leak_check", {}) or {}

    output_dir = Path(
        report_cfg.get(
            "output_dir",
            r"I:\Level 5 Documentation\Records\Calibration Certificates",
        )
    )
    template_path = Path(
        report_cfg.get(
            "template_path",
            r"I:\Level 5 Documentation\Quality Forms\QF87 Calibration Certificate_Teststands_Rev 000.docx",
        )
    )

    return QualitySettings(
        pressure_points_psia=build_pressure_points(quality_cfg),
        pressure_tolerance_psia=_coerce_float(quality_cfg.get("pressure_tolerance_psia", 0.5)),
        settle_tolerance_psia=_coerce_float(quality_cfg.get("settle_tolerance_psia", 0.4)),
        settle_hold_s=_coerce_float(quality_cfg.get("settle_hold_s", 5.0)),
        settle_timeout_s=_coerce_float(quality_cfg.get("settle_timeout_s", 180.0)),
        static_hold_s=_coerce_float(quality_cfg.get("static_hold_s", 8.0)),
        sample_hz=_coerce_float(quality_cfg.get("sample_hz", 4.0)),
        leak_check_target_psia=_coerce_float(leak_cfg.get("target_psia", 100.0)),
        leak_check_duration_s=_coerce_float(leak_cfg.get("duration_s", 90.0)),
        leak_check_sample_hz=_coerce_float(leak_cfg.get("sample_hz", 4.0)),
        leak_check_max_rate_psi_per_min=_coerce_optional_float(
            leak_cfg.get("max_rate_psi_per_min", 0.2)
        ),
        leak_check_ramp_rate_psi_per_s=_coerce_float(
            leak_cfg.get("ramp_rate_psi_per_s", 8.0)
        ),
        report_output_dir=output_dir,
        report_template_path=template_path,
        report_filename_prefix=str(report_cfg.get("filename_prefix", "QualityCalibration")),
    )


def setup_logging(config: dict[str, Any]) -> None:
    log_cfg = config.get("logging", {})
    level = getattr(logging, str(log_cfg.get("level", "INFO")).upper(), logging.INFO)
    log_dir = Path(log_cfg.get("log_dir", "logs"))
    if not log_dir.is_absolute():
        log_dir = get_default_config_path().parent / log_dir
    log_dir.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    brief_formatter = logging.Formatter("%(levelname)s: %(message)s")

    current_log = log_dir / "quality_cal.log"
    session_log = log_dir / f"quality_cal_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)
        try:
            handler.close()
        except Exception:
            pass

    console = logging.StreamHandler()
    console.setLevel(level)
    console.setFormatter(brief_formatter)

    rotating = logging.handlers.RotatingFileHandler(
        current_log,
        maxBytes=int(log_cfg.get("max_bytes", 10_485_760)),
        backupCount=int(log_cfg.get("backup_count", 5)),
        encoding="utf-8",
    )
    rotating.setLevel(level)
    rotating.setFormatter(formatter)

    session = logging.FileHandler(session_log, encoding="utf-8")
    session.setLevel(level)
    session.setFormatter(formatter)

    root_logger.addHandler(console)
    root_logger.addHandler(rotating)
    root_logger.addHandler(session)

    logger.info("Logging configured")
    logger.info("Log file: %s", current_log)


def _build_range(start: float, stop: float, step: float) -> list[float]:
    if step <= 0:
        return []
    if start > stop:
        return []
    values: list[float] = []
    current = start
    while current <= stop + 1e-9:
        values.append(round(current, 4))
        current += step
    return values


def _normalize_points(points: list[float]) -> list[float]:
    cleaned = sorted({round(point, 4) for point in points if point > 0.0})
    return cleaned


def _coerce_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Expected numeric value, got {value!r}") from exc


def _coerce_optional_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    return _coerce_float(value)
