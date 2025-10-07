"""OpenAI-style animated agent status widget.

Shows agent activity with fading text animation in the toolbar.
"""

from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, Property
from PySide6.QtGui import QPainter, QColor, QPaintEvent
from PySide6.QtWidgets import QWidget, QLabel, QHBoxLayout

log = logging.getLogger("scrabgpt.ui.agent_status")


class FadingLabel(QLabel):
    """Label with smooth opacity animation."""
    
    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self._opacity = 0.0
        
        # Animation
        self.fade_animation = QPropertyAnimation(self, b"opacity")
        self.fade_animation.setDuration(800)  # 800ms fade
        self.fade_animation.setEasingCurve(QEasingCurve.Type.InOutQuad)
    
    def get_opacity(self) -> float:
        """Get current opacity."""
        return self._opacity
    
    def set_opacity(self, value: float) -> None:
        """Set opacity and trigger repaint."""
        self._opacity = max(0.0, min(1.0, value))
        self.update()
    
    opacity = Property(float, get_opacity, set_opacity)
    
    def paintEvent(self, event: QPaintEvent) -> None:
        """Paint with opacity."""
        painter = QPainter(self)
        painter.setOpacity(self._opacity)
        super().paintEvent(event)
        painter.end()
    
    def fade_in(self) -> None:
        """Fade in animation."""
        self.fade_animation.stop()
        self.fade_animation.setStartValue(self._opacity)
        self.fade_animation.setEndValue(1.0)
        self.fade_animation.start()
    
    def fade_out(self) -> None:
        """Fade out animation."""
        self.fade_animation.stop()
        self.fade_animation.setStartValue(self._opacity)
        self.fade_animation.setEndValue(0.0)
        self.fade_animation.start()


class AgentStatusWidget(QWidget):
    """OpenAI-style animated status widget for agent activity.
    
    Shows:
    - Animated dots when agent is working
    - Fading status text
    - Smooth transitions between states
    
    Example:
        "🤖 Získavam jazyky..."
        "🤖 Analyzing board..."
    """
    
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        
        self.current_agent: Optional[str] = None
        self.current_status: Optional[str] = None
        self.dot_count = 0
        
        self._setup_ui()
        
        # Animation timer for dots
        self.dot_timer = QTimer(self)
        self.dot_timer.timeout.connect(self._update_dots)
        self.dot_timer.setInterval(500)  # Update every 500ms
        
        # Auto-hide timer
        self.hide_timer = QTimer(self)
        self.hide_timer.timeout.connect(self._auto_hide)
        self.hide_timer.setSingleShot(True)
    
    def _setup_ui(self) -> None:
        """Setup UI components."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 2, 8, 2)
        layout.setSpacing(6)
        
        # Status label with fading animation
        self.status_label = FadingLabel()
        self.status_label.setStyleSheet(
            "QLabel { "
            "color: #4caf50; "
            "font-size: 12px; "
            "padding: 4px; "
            "}"
        )
        layout.addWidget(self.status_label)
        
        # Initially hidden
        self.setVisible(False)
    
    def show_agent_activity(self, agent_name: str, status: str) -> None:
        """Show agent activity with animation.
        
        Args:
            agent_name: Name of the agent
            status: Status message
        """
        self.current_agent = agent_name
        self.current_status = status
        
        # Update text
        self._update_status_text()
        
        # Show widget with fade in
        if not self.isVisible():
            self.setVisible(True)
            self.status_label.fade_in()
        
        # Start dot animation
        if not self.dot_timer.isActive():
            self.dot_count = 0
            self.dot_timer.start()
        
        # Reset auto-hide timer
        self.hide_timer.stop()
    
    def hide_agent_activity(self, delay_ms: int = 2000) -> None:
        """Hide agent activity with optional delay.
        
        Args:
            delay_ms: Delay in milliseconds before hiding (default: 2s)
        """
        # Stop dot animation
        self.dot_timer.stop()
        
        if delay_ms > 0:
            # Schedule hide
            self.hide_timer.start(delay_ms)
        else:
            # Hide immediately
            self._auto_hide()
    
    def update_status(self, status: str) -> None:
        """Update status text while keeping agent visible.
        
        Args:
            status: New status message
        """
        self.current_status = status
        self._update_status_text()
    
    def _update_status_text(self) -> None:
        """Update status label text with current status and dots."""
        if not self.current_agent or not self.current_status:
            return
        
        # Create dots animation (1-3 dots)
        dots = "." * (self.dot_count + 1)
        
        # Format: "🤖 Agent: Status..."
        text = f"🤖 {self.current_agent}: {self.current_status}{dots}"
        
        self.status_label.setText(text)
    
    def _update_dots(self) -> None:
        """Update dot animation."""
        self.dot_count = (self.dot_count + 1) % 3
        self._update_status_text()
    
    def _auto_hide(self) -> None:
        """Auto-hide with fade out animation."""
        self.status_label.fade_out()
        
        # Hide widget after fade completes
        QTimer.singleShot(
            self.status_label.fade_animation.duration(),
            lambda: self.setVisible(False)
        )
        
        # Clear state
        self.current_agent = None
        self.current_status = None
        self.dot_count = 0
