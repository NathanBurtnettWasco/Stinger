"""
Database operations for Stinger.

Provides high-level functions for:
- Validating shop orders
- Loading test parameters
- Saving/updating test results
- Serial number management
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError

from .models import OrderCalibrationMaster, ProductTestParameters, OrderCalibrationDetail
from .session import session_scope

logger = logging.getLogger(__name__)


def validate_shop_order(shop_order: str) -> Optional[Dict[str, Any]]:
    """
    Validate a shop order and return work order details.
    
    Args:
        shop_order: The shop order number to validate.
        
    Returns:
        Dictionary with work order details, or None if not found.
    """
    if not shop_order:
        return None
    
    try:
        with session_scope() as session:
            shop_order_clean = shop_order.strip()
            records = session.query(OrderCalibrationMaster).filter_by(
                ShopOrder=shop_order_clean
            ).all()
            record = None
            if records:
                if len(records) > 1:
                    record = max(
                        records,
                        key=lambda item: (
                            item.CalibrationDate or datetime.min,
                            item.StartTime or datetime.min,
                        ),
                    )
                    logger.warning(
                        'Shop order lookup returned %d rows for %s; using the latest record',
                        len(records),
                        shop_order_clean,
                    )
                else:
                    record = records[0]
            
            if record:
                # Convert to dictionary, stripping fixed-width padding
                order_qty = record.OrderQTY
                details = {
                    'ShopOrder': record.ShopOrder.strip() if record.ShopOrder else None,
                    'PartID': record.PartID.strip() if record.PartID else None,
                    'SequenceID': record.LastSequenceCalibrated.strip() if record.LastSequenceCalibrated else None,
                    'OrderQTY': order_qty,
                    'OrderQty': order_qty,
                    'OperatorID': record.OperatorID.strip() if record.OperatorID else None,
                    'EquipmentID': record.EquipmentID.strip() if record.EquipmentID else None,
                }
                logger.info(f"Shop order validated: {shop_order}")
                return details
            else:
                logger.warning(f"Shop order not found: {shop_order}")
                return None
                
    except SQLAlchemyError as e:
        logger.error(f"Database error validating shop order: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error validating shop order: {e}")
        return None


def load_test_parameters(part_id: str, sequence_id: str) -> Dict[str, str]:
    """
    Load test parameters for a part/sequence combination.
    
    Args:
        part_id: Part ID from work order.
        sequence_id: Sequence ID from work order.
        
    Returns:
        Dictionary mapping ParameterName -> ParameterValue.
    """
    if not part_id or not sequence_id:
        return {}
    
    try:
        with session_scope() as session:
            # Normalize sequence ID (may be stored with or without zero-padding)
            seq_normalized = str(int(sequence_id.strip()))
            
            # Query PTP
            results = session.query(ProductTestParameters).filter(
                ProductTestParameters.PartID == part_id.strip(),
                func.cast(func.rtrim(ProductTestParameters.SequenceID), sqlalchemy.Integer)
                == int(seq_normalized),
            ).all()
            
            # Convert to dictionary, stripping padding
            params = {}
            for row in results:
                name = row.ParameterName.strip() if row.ParameterName else None
                value = row.ParameterValue.strip() if row.ParameterValue else None
                if name:
                    params[name] = value
            
            logger.info(f"Loaded {len(params)} PTP parameters for {part_id}/{sequence_id}")
            return params
            
    except SQLAlchemyError as e:
        logger.error(f"Database error loading PTP: {e}")
        return {}
    except Exception as e:
        logger.error(f"Unexpected error loading PTP: {e}")
        return {}


# Workaround for the import
import sqlalchemy


def get_tested_serials(shop_order: str, part_id: str, sequence_id: str) -> Set[int]:
    """
    Get set of serial numbers already tested for a work order.
    
    Args:
        shop_order: Shop order number.
        part_id: Part ID.
        sequence_id: Sequence ID.
        
    Returns:
        Set of serial numbers that have been tested.
    """
    try:
        with session_scope() as session:
            # Normalize sequence
            seq_formatted = f"{int(sequence_id.strip()):04d}"
            
            results = session.query(OrderCalibrationDetail.SerialNumber).filter(
                OrderCalibrationDetail.ShopOrder == shop_order.strip(),
                OrderCalibrationDetail.PartID == part_id.strip(),
                OrderCalibrationDetail.SequenceID == seq_formatted,
            ).distinct().all()
            
            return {row[0] for row in results}
            
    except SQLAlchemyError as e:
        logger.error(f"Database error getting tested serials: {e}")
        return set()


def get_next_serial_number(
    shop_order: str, 
    part_id: str, 
    sequence_id: str,
    in_progress_serials: Set[int] = None,
    start_from: int = 1
) -> int:
    """
    Get the next available serial number for a work order.
    
    Args:
        shop_order: Shop order number.
        part_id: Part ID.
        sequence_id: Sequence ID.
        in_progress_serials: Set of serials currently being tested on other ports.
        start_from: Minimum serial number to consider.
        
    Returns:
        Next available serial number.
    """
    if in_progress_serials is None:
        in_progress_serials = set()
    
    # Get already-tested serials from database
    tested = get_tested_serials(shop_order, part_id, sequence_id)
    
    # Find next available
    serial = start_from
    while serial in tested or serial in in_progress_serials:
        serial += 1
    
    return serial


def save_test_result(
    shop_order: str,
    part_id: str,
    sequence_id: str,
    serial_number: int,
    increasing_activation: float,
    decreasing_deactivation: float,
    in_spec: bool,
    temperature_c: float,
    units_of_measure: str,
    operator_id: str,
    equipment_id: str,
    activation_id: int = 1
) -> bool:
    """
    Save or update a test result.
    
    Implements UPDATE behavior for retests - updates existing row if present.
    
    Args:
        shop_order: Shop order number.
        part_id: Part ID.
        sequence_id: Sequence ID.
        serial_number: Unit serial number.
        increasing_activation: Measured activation pressure (increasing direction).
        decreasing_deactivation: Measured deactivation pressure (decreasing direction).
        in_spec: True if passed, False if failed.
        temperature_c: Ambient test temperature in Celsius.
        units_of_measure: Units string for display.
        operator_id: Operator who performed the test.
        equipment_id: Equipment identifier.
        activation_id: Attempt identifier (usually 1).
        
    Returns:
        True if save successful.
    """
    action = 'Saved'
    try:
        with session_scope() as session:
            # Format sequence ID with zero-padding
            seq_formatted = f"{int(sequence_id.strip()):04d}"
            
            # Check if record exists
            existing = session.query(OrderCalibrationDetail).filter_by(
                ShopOrder=shop_order.strip(),
                SequenceID=seq_formatted,
                PartID=part_id.strip(),
                SerialNumber=serial_number,
                ActivationID=activation_id
            ).one_or_none()
            
            if existing:
                # Update existing record
                existing.IncreasingActivation = increasing_activation
                existing.DecreasingDeactivation = decreasing_deactivation
                existing.TemperatureC = temperature_c
                existing.IncreasingGap = 0
                existing.DecreasingGap = 0
                existing.InSpec = in_spec
                existing.UnitsOfMeasure = units_of_measure
                existing.InspectionDate = datetime.now()
                existing.OperatorID = operator_id
                existing.EquipmentID = equipment_id
                action = 'Updated'
            else:
                # Insert new record
                record = OrderCalibrationDetail(
                    ShopOrder=shop_order.strip(),
                    SequenceID=seq_formatted,
                    PartID=part_id.strip(),
                    SerialNumber=serial_number,
                    ActivationID=activation_id,
                    IncreasingActivation=increasing_activation,
                    DecreasingDeactivation=decreasing_deactivation,
                    TemperatureC=temperature_c,
                    IncreasingGap=0,
                    DecreasingGap=0,
                    InSpec=in_spec,
                    UnitsOfMeasure=units_of_measure,
                    InspectionDate=datetime.now(),
                    OperatorID=operator_id,
                    EquipmentID=equipment_id
                )
                session.add(record)
                action = 'Inserted'

        logger.info(f"{action} test result: SN={serial_number}, InSpec={in_spec}")
        return True
            
    except SQLAlchemyError as e:
        logger.error(f"Database error saving test result: {e}")
        return False


def get_work_order_progress(shop_order: str, part_id: str, sequence_id: str) -> Dict[str, int]:
    """
    Get progress for a work order.
    
    Args:
        shop_order: Shop order number.
        part_id: Part ID.
        sequence_id: Sequence ID.
        
    Returns:
        Dictionary with 'completed', 'passed', 'failed' counts.
    """
    try:
        with session_scope() as session:
            seq_formatted = f"{int(sequence_id.strip()):04d}"
            shop_order_clean = shop_order.strip()
            part_id_clean = part_id.strip()
            
            # Use window function to get the latest ActivationID per serial number
            # This is much more efficient than fetching all rows and grouping in Python
            from sqlalchemy import func, desc
            from sqlalchemy.orm import aliased
            
            # Subquery: get max ActivationID for each SerialNumber
            latest_per_serial = session.query(
                OrderCalibrationDetail.SerialNumber,
                func.max(OrderCalibrationDetail.ActivationID).label('max_activation_id')
            ).filter(
                OrderCalibrationDetail.ShopOrder == shop_order_clean,
                OrderCalibrationDetail.PartID == part_id_clean,
                OrderCalibrationDetail.SequenceID == seq_formatted,
            ).group_by(
                OrderCalibrationDetail.SerialNumber
            ).subquery()
            
            # Join to get the InSpec status for the latest attempt of each serial
            latest_results = session.query(
                OrderCalibrationDetail.InSpec
            ).join(
                latest_per_serial,
                (OrderCalibrationDetail.SerialNumber == latest_per_serial.c.SerialNumber) &
                (OrderCalibrationDetail.ActivationID == latest_per_serial.c.max_activation_id)
            ).all()
            
            # Count results
            completed = len(latest_results)
            passed = sum(1 for r in latest_results if r.InSpec)
            failed = completed - passed
            
            return {
                'completed': completed,
                'passed': passed,
                'failed': failed,
            }
            
    except SQLAlchemyError as e:
        logger.error(f"Database error getting progress: {e}")
        return {'completed': 0, 'passed': 0, 'failed': 0}
