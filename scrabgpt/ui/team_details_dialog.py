"""Team Details Dialog - shows team configuration in a nice table."""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QFrame,
)

from ..core.team_config import TeamConfig

log = logging.getLogger("scrabgpt.ui")


class TeamDetailsDialog(QDialog):
    """Dialog showing team configuration details in a table."""
    
    def __init__(
        self,
        parent: QDialog | None,
        team: TeamConfig,
    ) -> None:
        super().__init__(parent)
        self.team = team
        self.setWindowTitle(f"Team: {team.name}")
        self.setModal(True)
        self.resize(750, 500)
        
        self._setup_ui()
    
    def _setup_ui(self) -> None:
        """Setup UI components."""
        self.setStyleSheet(
            "QDialog { background-color: #0f1a12; color: #e8f5e9; }"
            "QLabel { color: #e8f5e9; }"
        )
        
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)
        
        # Header
        header_layout = QHBoxLayout()
        
        title = QLabel(f"🏆 {self.team.name}")
        title.setStyleSheet(
            "font-size: 18px; font-weight: bold; color: #4caf50; padding: 8px 0;"
        )
        header_layout.addWidget(title)
        
        header_layout.addStretch()
        
        provider_label = QLabel(f"Provider: {self.team.provider.upper()}")
        provider_label.setStyleSheet(
            "font-size: 13px; color: #b6e0bd; background: #1a3020; "
            "padding: 6px 12px; border-radius: 4px; border: 1px solid #2f5c39;"
        )
        header_layout.addWidget(provider_label)
        
        layout.addLayout(header_layout)
        
        # Info section
        info_frame = QFrame()
        info_frame.setStyleSheet(
            "QFrame { "
            "background: #132418; border: 1px solid #2f5c39; border-radius: 6px; "
            "padding: 12px; "
            "}"
        )
        info_layout = QVBoxLayout(info_frame)
        info_layout.setSpacing(6)
        
        model_count = QLabel(f"Models: {len(self.team.model_ids)}")
        model_count.setStyleSheet("font-size: 13px; color: #e8f5e9;")
        info_layout.addWidget(model_count)
        
        timeout = QLabel(f"Timeout: {self.team.timeout_seconds}s")
        timeout.setStyleSheet("font-size: 13px; color: #e8f5e9;")
        info_layout.addWidget(timeout)
        
        created = QLabel(f"Created: {self.team.created_at[:19]}")
        created.setStyleSheet("font-size: 12px; color: #81c784;")
        info_layout.addWidget(created)
        
        updated = QLabel(f"Updated: {self.team.updated_at[:19]}")
        updated.setStyleSheet("font-size: 12px; color: #81c784;")
        info_layout.addWidget(updated)
        
        layout.addWidget(info_frame)
        
        # Models table
        table_label = QLabel("Model IDs in Team:")
        table_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #4caf50; padding: 8px 0;")
        layout.addWidget(table_label)
        
        self.table = QTableWidget()
        self.table.setColumnCount(1)
        self.table.setHorizontalHeaderLabels(["Model ID"])
        
        # Green-themed table styling
        self.table.setStyleSheet("""
            QTableWidget {
                border: 1px solid #2f5c39;
                border-radius: 6px;
                background: #0a0a0a;
                gridline-color: #1a3020;
                color: #e8f5e9;
                font-size: 13px;
            }
            QTableWidget::item {
                padding: 10px;
                border-bottom: 1px solid #132418;
            }
            QTableWidget::item:selected {
                background: #295c33;
                color: #e8f5e9;
            }
            QHeaderView::section {
                background: #1a3020;
                color: #4caf50;
                padding: 10px;
                border: none;
                border-bottom: 2px solid #2f5c39;
                font-weight: bold;
                font-size: 12px;
            }
        """)
        
        # Configure headers
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)  # Model ID
        
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        
        # Populate table with model IDs
        self.table.setRowCount(len(self.team.model_ids))
        for i, model_id in enumerate(self.team.model_ids):
            # Model ID
            id_item = QTableWidgetItem(model_id)
            id_item.setForeground(Qt.GlobalColor.white)
            self.table.setItem(i, 0, id_item)
        
        layout.addWidget(self.table, 1)
        
        # Close button
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        close_btn = QPushButton("Zavrieť")
        close_btn.setStyleSheet(
            "QPushButton { "
            "background: #2e7d32; color: #e8f5e9; border: 1px solid #4caf50; "
            "border-radius: 4px; padding: 10px 24px; font-size: 13px; font-weight: bold; "
            "} "
            "QPushButton:hover { background: #388e3c; } "
            "QPushButton:pressed { background: #1b5e20; }"
        )
        close_btn.clicked.connect(self.accept)
        button_layout.addWidget(close_btn)
        
        layout.addLayout(button_layout)
