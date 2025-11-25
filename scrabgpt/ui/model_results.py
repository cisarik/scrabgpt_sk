"""AI Model Results Table - displays competition results with eye-candy styling."""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import Qt, QTimer, QEvent, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem,
    QHeaderView,
)

from .response_detail import ResponseDetailDialog

log = logging.getLogger("scrabgpt.ui")

_PENDING_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]


class AIModelResultsTable(QWidget):
    """Eye-candy table showing AI model competition results.
    
    Displays:
    - Model rank (1st, 2nd, 3rd, etc.)
    - Model name
    - Proposed word/move
    - Score
    - Judge validation (✓/✗)
    - Status
    
    Styling:
    - Winner (rank 1 + valid): bold, white background
    - Valid moves: green text
    - Invalid moves: gray/semi-transparent
    - Errors: red text
    
    Sorted by score (highest first).
    """
    
    agent_row_clicked = Signal(str, str)  # model_id, model_name
    
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.results: list[dict[str, Any]] = []
        self._results_by_model: dict[str, dict[str, Any]] = {}
        self._pending_timer = QTimer(self)
        self._pending_timer.setInterval(200)
        self._pending_timer.timeout.connect(self._on_pending_tick)
        self._pending_phase = 0
        self.setup_ui()
    
    def setup_ui(self) -> None:
        """Initialize the UI components."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 0)
        layout.setSpacing(0)
        
        # Results table (always visible, just empty when no results)
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels([
            "🏅", "Model", "Move", "Score", "✓", "Status"
        ])
        
        # Table styling - Dark mode to match UI
        self.table.setStyleSheet("""
            QTableWidget {
                border: 1px solid #444;
                border-radius: 4px;
                background: #1a1a1a;
                gridline-color: #333;
                color: white;
                font-size: 13px;
            }
            QTableWidget::item {
                padding: 8px;
                border-bottom: 1px solid #2a2a2a;
            }
            QHeaderView::section {
                background: #2a2a2a;
                color: white;
                padding: 8px;
                border: none;
                border-bottom: 2px solid #444;
                font-weight: bold;
                font-size: 12px;
            }
        """)
        
        # Configure headers
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)  # Rank
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)  # Model
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)  # Move
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)  # Score
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)  # Valid
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)  # Status
        
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        
        # Make rows clickable
        self.table.cellClicked.connect(self._on_cell_clicked)
        self.table.setMouseTracking(True)
        self.table.viewport().setMouseTracking(True)
        self.table.cellEntered.connect(self._on_cell_entered)
        self.table.viewport().installEventFilter(self)
        self.table.viewport().setCursor(Qt.CursorShape.ArrowCursor)
        
        # Set minimum/maximum height
        self.table.setMinimumHeight(0)  # Allow collapsing when empty
        self.table.setMaximumHeight(250)
        
        layout.addWidget(self.table)
        
        # Start with empty table (visible but collapsed)
        self.table.setRowCount(0)

    def _on_cell_entered(self, _row: int, column: int) -> None:
        """Adjust cursor when hovering over table cells."""
        if column == 1:
            self.table.viewport().setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            self.table.viewport().setCursor(Qt.CursorShape.ArrowCursor)

    def eventFilter(self, obj, event) -> bool:
        """Reset cursor when leaving the table viewport."""
        if obj is self.table.viewport() and event.type() == QEvent.Type.Leave:
            self.table.viewport().setCursor(Qt.CursorShape.ArrowCursor)
        return super().eventFilter(obj, event)
    
    def set_results(self, results: list[dict[str, Any]]) -> None:
        """Replace current results with a new list (final render)."""

        if not results:
            self.clear_results()
            return

        mapped: dict[str, dict[str, Any]] = {}
        for result in results:
            model_id = result.get("model")
            if model_id is None:
                continue
            existing = self._results_by_model.get(model_id, {})
            if "order" in existing and "order" not in result:
                merged_result = dict(result)
                merged_result["order"] = existing["order"]
                mapped[model_id] = merged_result
            else:
                mapped[model_id] = result

        self._results_by_model = mapped
        self._render_results()

    def initialize_models(self, models: list[dict[str, Any]]) -> None:
        """Pre-populate table with pending entries for selected models."""

        pending_entries: dict[str, dict[str, Any]] = {}
        for order_index, model in enumerate(models):
            model_id = model.get("id") or model.get("model")
            if not model_id:
                continue
            pending_entries[model_id] = {
                "model": model_id,
                "model_name": model.get("name", model_id),
                "status": "pending",
                "score": None,
                "words": [],
                "judge_valid": None,
                "error": None,
                "order": order_index,
            }

        self._results_by_model = pending_entries
        self._render_results()

    def update_result(self, result: dict[str, Any]) -> None:
        """Merge a single model result and re-render the table."""

        model_id = result.get("model") or result.get("id")
        if not model_id:
            # Some specialized updates (like timer) might not have a model ID
            # and we don't want to log warnings for them if they are not meant for this table.
            if result.get("status") == "timer":
                return
            log.warning("Ignoring partial result without model id: %s", result)
            return

        if model_id == "timer":
             return

        existing = self._results_by_model.get(model_id, {})
        merged = {**existing, **result}
        self._results_by_model[model_id] = merged
        self._render_results()

    def _render_results(self) -> None:
        """Render internal results dictionary into the table widget."""

        if not self._results_by_model:
            self.table.setRowCount(0)
            self.table.setMinimumHeight(0)
            self.results = []
            return

        records = list(self._results_by_model.values())

        def normalize_score(value: Any) -> int:
            try:
                return int(value)
            except (TypeError, ValueError):
                return -1

        def sort_key(r: dict[str, Any]) -> tuple[int, int, int, str]:
            status = (r.get("status") or "error").lower()
            if status in {"ready", "pending"}:
                return (1, r.get("order", 0), 0, r.get("model_name", ""))

            status_priority = {
                "ok": 0,
                "invalid": 1,
                "parse_error": 2,
                "error": 3,
            }.get(status, 4)
            score_value = normalize_score(r.get("score"))
            return (0, -score_value, status_priority, r.get("model_name", ""))

        sorted_results = sorted(records, key=sort_key)

        self.results = sorted_results
        self.table.setRowCount(len(sorted_results))
        self.table.setMinimumHeight(180)

        for idx, result in enumerate(sorted_results):
            is_winner = idx == 0 and result.get("judge_valid", False)
            self._populate_row(idx, result, is_winner=is_winner)

        self.table.resizeRowsToContents()

        has_pending = any(
            (entry.get("status") or "").lower() == "pending"
            for entry in sorted_results
        )
        if has_pending:
            if not self._pending_timer.isActive():
                self._pending_phase = 0
                self._pending_timer.start()
        else:
            if self._pending_timer.isActive():
                self._pending_timer.stop()
                self._pending_phase = 0
    
    def _populate_row(self, row: int, result: dict[str, Any], is_winner: bool) -> None:
        """Populate a single row with result data."""

        model_name = result.get("model_name", result.get("model", "Unknown"))
        status_display = result.get("status", "error") or "error"
        status = status_display.lower()
        error = result.get("error")
        judge_valid = result.get("judge_valid")
        judge_reason = result.get("judge_reason", "")
        words = result.get("words", [])

        score_value = result.get("score")
        try:
            score_int = int(score_value)
        except (TypeError, ValueError):
            score_int = None

        # Determine styling (dark mode compatible)
        font_bold = False
        if is_winner:
            bg_color = QColor(34, 139, 34)
            text_color = QColor(255, 255, 255)
            font_bold = True
        elif status in {"pending", "ready"}:
            bg_color = QColor(40, 45, 70)
            text_color = QColor(190, 200, 235)
        elif status == "ok" and judge_valid:
            bg_color = QColor(28, 100, 28)
            text_color = QColor(144, 238, 144)
        elif status == "ok" and judge_valid is False:
            bg_color = QColor(50, 50, 50)
            text_color = QColor(200, 160, 120)
        elif status == "invalid":
            bg_color = QColor(60, 40, 40)
            text_color = QColor(250, 200, 120)
        elif status in {"parse_error", "exception"}:
            bg_color = QColor(75, 35, 35)
            text_color = QColor(255, 170, 130)
        else:
            bg_color = QColor(80, 20, 20)
            text_color = QColor(255, 120, 120)

        # Rank emoji (only show for actual results, not for pending status)
        if status == "pending":
            rank_text = self._pending_frame()
        elif status == "ready":
            rank_text = "⏳"
        else:
            rank_emoji = ["🥇", "🥈", "🥉"] if row < 3 else [f"{row + 1}."]
            rank_text = rank_emoji[row] if row < len(rank_emoji) else f"{row + 1}."
        
        rank_item = QTableWidgetItem(rank_text)
        rank_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        rank_item.setBackground(bg_color)
        rank_item.setForeground(text_color)
        if font_bold:
            font = rank_item.font()
            font.setBold(True)
            rank_item.setFont(font)
        self.table.setItem(row, 0, rank_item)
        
        # Model name
        model_item = QTableWidgetItem(model_name)
        model_item.setBackground(bg_color)
        model_item.setForeground(text_color)
        if font_bold:
            font = model_item.font()
            font.setBold(True)
            model_item.setFont(font)
        self.table.setItem(row, 1, model_item)
        
        # Move (words or error)
        if status in {"pending", "ready"}:
            move_text = "—"
        elif status == "ok" and words:
            move_text = ", ".join(words)
        elif error:
            error_lower = error.lower()
            if "empty response" in error_lower:
                move_text = "⚠️ Prázdna odpoveď"
            elif "unexpected response" in error_lower:
                move_text = "⚠️ Neplatná odpoveď"
            elif "json" in error_lower:
                move_text = "⚠️ Neplatný JSON"
            else:
                move_text = f"⚠️ {error[:40]}..."
        else:
            move_text = "—"
        
        move_item = QTableWidgetItem(move_text)
        move_item.setBackground(bg_color)
        move_item.setForeground(text_color)
        if font_bold:
            font = move_item.font()
            font.setBold(True)
            move_item.setFont(font)
        # Full error in tooltip
        tooltip_text = error or result.get("error_analysis") or move_text
        move_item.setToolTip(tooltip_text)
        self.table.setItem(row, 2, move_item)
        
        # Score
        if score_int is not None and score_int >= 0 and status not in {"pending", "ready"}:
            score_text = str(score_int)
        else:
            score_text = "—"
        score_item = QTableWidgetItem(score_text)
        score_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        score_item.setBackground(bg_color)
        score_item.setForeground(text_color)
        if font_bold:
            font = score_item.font()
            font.setBold(True)
            font.setPointSize(font.pointSize() + 1)
            score_item.setFont(font)
        self.table.setItem(row, 3, score_item)
        
        # Judge validation
        if judge_valid is True:
            valid_text = "✓"
            valid_color = QColor(46, 125, 50)
        elif judge_valid is False:
            valid_text = "✗"
            valid_color = QColor(198, 40, 40)
        else:
            valid_text = "—"
            valid_color = text_color
        
        valid_item = QTableWidgetItem(valid_text)
        valid_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        valid_item.setBackground(bg_color)
        valid_item.setForeground(valid_color)
        if font_bold:
            font = valid_item.font()
            font.setBold(True)
            font.setPointSize(font.pointSize() + 2)
            valid_item.setFont(font)
        if judge_reason:
            valid_item.setToolTip(judge_reason)
        self.table.setItem(row, 4, valid_item)
        
        # Status
        if status == "pending":
            status_text = "Čaká…"
        elif status == "ready":
            status_text = "Pripravený"
        elif status == "ok" and judge_valid:
            status_text = "Valid ✓"
        elif status == "ok" and judge_valid is False:
            status_text = "Invalid"
        elif status == "ok":
            status_text = "Dokončené"
        elif status == "parse_error":
            status_text = "Parse Error"
        elif status == "error":
            status_text = "API Error"
        else:
            status_text = status.title()
        
        status_item = QTableWidgetItem(status_text)
        status_item.setBackground(bg_color)
        status_item.setForeground(text_color)
        if font_bold:
            font = status_item.font()
            font.setBold(True)
            status_item.setFont(font)
        self.table.setItem(row, 5, status_item)

    def _pending_frame(self) -> str:
        return _PENDING_FRAMES[self._pending_phase % len(_PENDING_FRAMES)]

    def _on_pending_tick(self) -> None:
        if not any((r.get("status") or "").lower() == "pending" for r in self.results):
            if self._pending_timer.isActive():
                self._pending_timer.stop()
            self._pending_phase = 0
            return

        self._pending_phase = (self._pending_phase + 1) % len(_PENDING_FRAMES)
        frame = self._pending_frame()
        for idx, result in enumerate(self.results):
            if (result.get("status") or "").lower() != "pending":
                continue
            item = self.table.item(idx, 0)
            if item is not None:
                item.setText(frame)

    def clear_results(self) -> None:
        """Clear the results table."""
        self.table.setRowCount(0)
        self.table.setMinimumHeight(0)  # Collapse when empty
        self.results = []
        self._results_by_model = {}
        if self._pending_timer.isActive():
            self._pending_timer.stop()
        self._pending_phase = 0
    
    def _on_cell_clicked(self, row: int, column: int) -> None:
        """Handle cell click to show response details."""
        if 0 <= row < len(self.results):
            result = self.results[row]
            status = (result.get("status") or "").lower()
            model_id = str(result.get("model") or "")
            model_name = str(result.get("model_name") or model_id)
            
            # Agent rows: otvor chat namiesto detailu (aj pri pending)
            if model_id.startswith("agent:"):
                self.agent_row_clicked.emit(model_id, model_name)
                return
            
            if status in {"pending", "ready"}:
                return
            dialog = ResponseDetailDialog(result, parent=self)
            dialog.exec()
