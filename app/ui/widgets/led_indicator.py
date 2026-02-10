"""
High-resolution LED indicator widget for NO/NC switch status display.

Uses QPainter for crisp, anti-aliased rendering at any size.
"""

from typing import Optional

from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QRadialGradient
from PyQt6.QtWidgets import QWidget


class LEDIndicator(QWidget):
    """
    High-resolution LED indicator with glow effect.
    
    Renders a circular LED with smooth anti-aliasing and optional glow effect
    when active. Supports green (NO) and red (NC) colors.
    """
    
    def __init__(self, parent: Optional[QWidget] = None, size: int = 32):
        """
        Initialize LED indicator.
        
        Args:
            parent: Parent widget
            size: Size in pixels (default 32 for better visibility)
        """
        super().__init__(parent)
        self._size = size
        self._active = False
        self._is_nc = False  # True for NC (red), False for NO (green)
        
        self.setFixedSize(size, size)
        self.setMinimumSize(size, size)
        self.setMaximumSize(size, size)
        
    def set_active(self, active: bool) -> None:
        """Set the active state of the LED."""
        if self._active != active:
            self._active = active
            self.update()
    
    def set_nc_mode(self, is_nc: bool) -> None:
        """Set whether this is an NC indicator (red) or NO indicator (green)."""
        if self._is_nc != is_nc:
            self._is_nc = is_nc
            self.update()
    
    def sizeHint(self) -> QSize:
        """Return the preferred size."""
        return QSize(self._size, self._size)
    
    def paintEvent(self, event) -> None:
        """Paint the LED with high-quality rendering."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        
        rect = self.rect()
        center_x = rect.width() / 2
        center_y = rect.height() / 2
        radius = min(rect.width(), rect.height()) / 2 - 2  # Leave 2px margin
        
        # Determine colors based on state
        if self._active:
            if self._is_nc:
                # NC active: red
                base_color = QColor(220, 38, 38)  # #dc2626
                glow_color = QColor(220, 38, 38, 150)
            else:
                # NO active: green
                base_color = QColor(22, 163, 74)  # #16a34a
                glow_color = QColor(22, 163, 74, 150)
        else:
            # Inactive: light grey
            base_color = QColor(209, 213, 219)  # #d1d5db
            glow_color = QColor(0, 0, 0, 0)  # No glow when inactive
        
        # Draw glow effect when active
        if self._active:
            glow_radius = radius + 6
            glow_gradient = QRadialGradient(center_x, center_y, glow_radius)
            glow_gradient.setColorAt(0.0, glow_color)
            glow_gradient.setColorAt(0.5, QColor(glow_color.red(), glow_color.green(), glow_color.blue(), 80))
            glow_gradient.setColorAt(1.0, QColor(glow_color.red(), glow_color.green(), glow_color.blue(), 0))
            
            painter.setBrush(QBrush(glow_gradient))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(int(center_x - glow_radius), int(center_y - glow_radius),
                              int(glow_radius * 2), int(glow_radius * 2))
        
        # Draw LED body with gradient for depth
        led_gradient = QRadialGradient(center_x, center_y, radius)
        if self._active:
            # Bright center, slightly darker edges for depth
            led_gradient.setColorAt(0.0, base_color.lighter(120))
            led_gradient.setColorAt(0.7, base_color)
            led_gradient.setColorAt(1.0, base_color.darker(110))
        else:
            # Flat grey when inactive
            led_gradient.setColorAt(0.0, base_color)
            led_gradient.setColorAt(1.0, base_color)
        
        painter.setBrush(QBrush(led_gradient))
        
        # Draw border
        border_color = base_color if self._active else QColor(0, 0, 0, 25)
        pen = QPen(border_color, 2)
        painter.setPen(pen)
        
        painter.drawEllipse(int(center_x - radius), int(center_y - radius),
                          int(radius * 2), int(radius * 2))
        
        # Draw highlight for active LEDs
        if self._active:
            highlight_radius = radius * 0.3
            highlight_gradient = QRadialGradient(center_x - radius * 0.3, center_y - radius * 0.3, highlight_radius)
            highlight_gradient.setColorAt(0.0, QColor(255, 255, 255, 120))
            highlight_gradient.setColorAt(1.0, QColor(255, 255, 255, 0))
            
            painter.setBrush(QBrush(highlight_gradient))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(int(center_x - radius * 0.3 - highlight_radius),
                              int(center_y - radius * 0.3 - highlight_radius),
                              int(highlight_radius * 2), int(highlight_radius * 2))
