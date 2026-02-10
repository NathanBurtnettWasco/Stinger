"""
Configuration loader for Stinger.

Loads and validates the stinger_config.yaml file.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from app.services.control_config import ControlConfigError, parse_control_config

logger = logging.getLogger(__name__)

# Default config file location (relative to project root)
DEFAULT_CONFIG_PATH = Path(__file__).parent.parent.parent / "stinger_config.yaml"
MEASUREMENT_SOURCE_TRANSDUCER = 'transducer'
MEASUREMENT_SOURCE_ALICAT = 'alicat'
VALID_MEASUREMENT_SOURCES = {
    MEASUREMENT_SOURCE_TRANSDUCER,
    MEASUREMENT_SOURCE_ALICAT,
}


def normalize_measurement_source(value: Any) -> str:
    """Normalize configured pressure source value to a supported token."""
    normalized = str(value or MEASUREMENT_SOURCE_TRANSDUCER).strip().lower()
    if normalized not in VALID_MEASUREMENT_SOURCES:
        logger.warning(
            'Invalid hardware.measurement.preferred_source=%r; defaulting to %s',
            value,
            MEASUREMENT_SOURCE_TRANSDUCER,
        )
        return MEASUREMENT_SOURCE_TRANSDUCER
    return normalized


def apply_measurement_defaults(config: Dict[str, Any]) -> None:
    """Ensure measurement-source settings exist and are normalized."""
    hardware_cfg = config.setdefault('hardware', {})
    if not isinstance(hardware_cfg, dict):
        raise ValueError('Config section "hardware" must be a mapping')

    measurement_cfg = hardware_cfg.setdefault('measurement', {})
    if not isinstance(measurement_cfg, dict):
        raise ValueError('Config section "hardware.measurement" must be a mapping')

    measurement_cfg['preferred_source'] = normalize_measurement_source(
        measurement_cfg.get('preferred_source', MEASUREMENT_SOURCE_TRANSDUCER)
    )
    measurement_cfg['fallback_on_unavailable'] = bool(
        measurement_cfg.get('fallback_on_unavailable', True)
    )


def _validate_required_sections(config: Dict[str, Any]) -> None:
    """Validate required top-level config sections."""
    required_sections = ['app', 'hardware', 'control', 'timing', 'database', 'ui']
    for section in required_sections:
        if section not in config:
            raise ValueError(f"Missing required config section: {section}")

    if 'labjack' not in config['hardware']:
        raise ValueError("Missing required hardware section: labjack")


def load_config(config_path: Optional[Path] = None) -> Dict[str, Any]:
    """Load configuration from YAML file."""
    path = config_path or DEFAULT_CONFIG_PATH
    
    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found: {path}")
    
    logger.info(f"Loading configuration from {path}")
    
    with open(path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)

    if not isinstance(config, dict):
        raise ValueError('Configuration root must be a mapping')
    _validate_required_sections(config)
    apply_measurement_defaults(config)
    try:
        parse_control_config(config)
    except ControlConfigError as exc:
        raise ValueError(f'Invalid control configuration: {exc}') from exc
    
    logger.info(f"Configuration loaded: {config['app']['name']} v{config['app']['version']}")
    return config


def save_config(config: Dict[str, Any], config_path: Optional[Path] = None) -> Path:
    """Persist configuration to YAML file after normalization/validation."""
    if not isinstance(config, dict):
        raise ValueError('Configuration root must be a mapping')
    _validate_required_sections(config)
    apply_measurement_defaults(config)
    try:
        parse_control_config(config)
    except ControlConfigError as exc:
        raise ValueError(f'Invalid control configuration: {exc}') from exc

    path = config_path or DEFAULT_CONFIG_PATH
    logger.info('Saving configuration to %s', path)
    with open(path, 'w', encoding='utf-8') as f:
        yaml.safe_dump(config, f, sort_keys=False)
    return path


def get_port_config(config: Dict[str, Any], port_id: str) -> Dict[str, Any]:
    """Get configuration for a specific port (port_a or port_b)."""
    labjack_config = config['hardware']['labjack'].get(port_id, {})
    alicat_config = config['hardware']['alicat'].get(port_id, {})

    
    # Merge with common Alicat settings
    alicat_common = {
        'com_port': config['hardware']['alicat'].get('com_port'),
        'baudrate': config['hardware']['alicat'].get('baudrate'),
        'timeout_s': config['hardware']['alicat'].get('timeout_s'),
    }
    alicat_config = {**alicat_common, **alicat_config}

    return {
        'labjack': labjack_config,
        'alicat': alicat_config,
        'solenoid': config['hardware'].get('solenoid', {}),
    }


def setup_logging(config: Dict[str, Any]) -> None:
    """Configure logging with file and console handlers."""
    import logging.handlers
    
    log_cfg = config.get('logging', {})
    level = getattr(logging, log_cfg.get('level', 'DEBUG'))
    log_dir = Path(log_cfg.get('log_dir', 'logs'))
    if not log_dir.is_absolute():
        project_root = DEFAULT_CONFIG_PATH.parent
        log_dir = project_root / log_dir
    max_bytes = log_cfg.get('max_bytes', 10_485_760)  # 10MB
    backup_count = log_cfg.get('backup_count', 5)
    
    # Ensure log directory exists
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # Create formatters
    brief_formatter = logging.Formatter('%(levelname)s: %(message)s')
    detailed_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(brief_formatter)
    
    # File handler
    current_log_path = log_dir / 'stinger.log'
    file_handler = logging.handlers.RotatingFileHandler(
        current_log_path,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding='utf-8',
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(detailed_formatter)

    session_log_name = f"stinger_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    session_log_path = log_dir / session_log_name
    session_file_handler = logging.FileHandler(session_log_path, encoding='utf-8')
    session_file_handler.setLevel(level)
    session_file_handler.setFormatter(detailed_formatter)
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Prevent duplicate handlers when setup is called repeatedly in-process.
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)
        try:
            handler.close()
        except Exception:
            pass

    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(session_file_handler)
    
    # Module-specific levels
    logging.getLogger('stinger.hardware').setLevel(logging.INFO)
    logging.getLogger('stinger.ui').setLevel(logging.INFO)
    logging.getLogger('stinger.database').setLevel(logging.INFO)
    
    logger.info("Logging configured")
    logger.info("Log file: %s", current_log_path)
    logger.info("Session log file: %s", session_log_path)
