"""
Database session management.

Provides SQLAlchemy session factory and context manager for database operations.
"""

import logging
from contextlib import contextmanager
from typing import Any, Dict, Generator, Optional

from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

logger = logging.getLogger(__name__)

# Global engine and session factory
_engine: Optional[Engine] = None
_SessionFactory: Optional[sessionmaker] = None


def initialize_database(config: Dict[str, Any]) -> bool:
    """
    Initialize the database connection.
    
    Args:
        config: Database configuration from stinger_config.yaml
        
    Returns:
        True if connection successful.
    """
    global _engine, _SessionFactory
    
    try:
        # Build connection string for SQL Server
        server = config.get('server', 'PASCAL')
        database = config.get('database', 'WASCO_Calibration')
        driver = config.get('driver', 'ODBC Driver 18 for SQL Server')
        timeout = config.get('connection_timeout_sec', 5)
        
        # Use Windows authentication by default, or username/password if provided
        username = config.get('username')
        password = config.get('password')
        
        if username and password:
            connection_url = URL.create(
                "mssql+pyodbc",
                username=username,
                password=password,
                host=server,
                database=database,
                query={
                    "driver": driver,
                    "TrustServerCertificate": "yes",
                },
            )
        else:
            # Windows authentication
            connection_url = URL.create(
                "mssql+pyodbc",
                host=server,
                database=database,
                query={
                    "driver": driver,
                    "TrustServerCertificate": "yes",
                    "Trusted_Connection": "yes",
                },
            )
        
        _engine = create_engine(
            connection_url,
            pool_pre_ping=True,
            pool_recycle=3600,
            connect_args={'timeout': int(timeout)}
        )
        
        # Test connection
        with _engine.connect() as conn:
            conn.exec_driver_sql("SELECT 1")
        
        _SessionFactory = sessionmaker(bind=_engine)
        
        logger.info(f"Database connected: {server}/{database}")
        return True
        
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        return False


def get_engine() -> Optional[Engine]:
    """Get the SQLAlchemy engine."""
    return _engine


def get_db_session() -> Optional[Session]:
    """
    Get a new database session.
    
    Returns:
        SQLAlchemy Session, or None if not initialized.
    """
    if _SessionFactory is None:
        logger.error("Database not initialized - call initialize_database() first")
        return None
    return _SessionFactory()


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """
    Provide a transactional scope around a series of operations.
    
    Usage:
        with session_scope() as session:
            session.query(...)
            session.add(...)
        # Auto-commits on success, rolls back on exception
    """
    if _SessionFactory is None:
        raise RuntimeError("Database not initialized - call initialize_database() first")
    
    session = _SessionFactory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def close_database() -> None:
    """Close the database connection."""
    global _engine, _SessionFactory
    
    if _engine:
        _engine.dispose()
        _engine = None
        _SessionFactory = None
        logger.info("Database connection closed")
