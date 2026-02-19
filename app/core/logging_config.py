"""Logging configuration helpers for Stinger."""

from __future__ import annotations

import logging
import logging.handlers
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)


def setup_logging(config: Dict[str, Any], project_root: Path) -> None:
    """Configure process logging with console and rotating file handlers."""
    log_cfg = config.get('logging', {})
    level = getattr(logging, log_cfg.get('level', 'DEBUG'))
    log_dir = Path(log_cfg.get('log_dir', 'logs'))
    if not log_dir.is_absolute():
        log_dir = project_root / log_dir
    max_bytes = log_cfg.get('max_bytes', 10_485_760)  # 10MB
    backup_count = log_cfg.get('backup_count', 5)

    log_dir.mkdir(parents=True, exist_ok=True)

    brief_formatter = logging.Formatter('%(levelname)s: %(message)s')
    detailed_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    )

    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(brief_formatter)

    current_log_path = log_dir / 'stinger.log'
    file_handler = logging.handlers.RotatingFileHandler(
        current_log_path,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding='utf-8',
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(detailed_formatter)

    session_log_name = f'stinger_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'
    session_log_path = log_dir / session_log_name
    session_file_handler = logging.FileHandler(session_log_path, encoding='utf-8')
    session_file_handler.setLevel(level)
    session_file_handler.setFormatter(detailed_formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)
        try:
            handler.close()
        except Exception:
            pass

    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(session_file_handler)

    logging.getLogger('stinger.hardware').setLevel(logging.INFO)
    logging.getLogger('stinger.ui').setLevel(logging.INFO)
    logging.getLogger('stinger.database').setLevel(logging.INFO)

    logger.info('Logging configured')
    logger.info('Log file: %s', current_log_path)
    logger.info('Session log file: %s', session_log_path)
