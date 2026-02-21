"""AI model attempts table for multi-model planning transparency."""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import Qt, QTimer, QEvent, Signal, QObject, QSize
from PySide6.QtGui import QColor, QTextDocument, QBrush
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QApplication,
    QStyle,
)

from .response_detail import ResponseDetailDialog

log = logging.getLogger("scrabgpt.ui")

_PENDING_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]


class _AttemptsRichTextDelegate(QStyledItemDelegate):
    """Render HTML in attempts column so only the best attempt can be bold."""

    def paint(
        self,
        painter: Any,
        option: QStyleOptionViewItem,
        index: Any,
    ) -> None:
        html_value = index.data(Qt.ItemDataRole.UserRole)
        if not isinstance(html_value, str) or not html_value.strip():
            super().paint(painter, option, index)
            return

        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.text = ""

        style = opt.widget.style() if opt.widget else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, opt.widget)

        foreground = index.data(Qt.ItemDataRole.ForegroundRole)
        color_name = "#ffffff"
        if isinstance(foreground, QBrush):
            color_name = foreground.color().name()

        doc = QTextDocument()
        doc.setDefaultFont(opt.font)
        doc.setHtml(f'<span style="color:{color_name};">{html_value}</span>')

        text_rect = style.subElementRect(
            QStyle.SubElement.SE_ItemViewItemText,
            opt,
            opt.widget,
        )
        doc.setTextWidth(float(text_rect.width()))

        painter.save()
        painter.translate(text_rect.topLeft())
        y_offset = max(0.0, (text_rect.height() - doc.size().height()) / 2.0)
        painter.translate(0.0, y_offset)
        doc.drawContents(painter)
        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index: Any) -> QSize:
        html_value = index.data(Qt.ItemDataRole.UserRole)
        if not isinstance(html_value, str) or not html_value.strip():
            return super().sizeHint(option, index)

        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        doc = QTextDocument()
        doc.setDefaultFont(opt.font)
        doc.setHtml(html_value)
        return QSize(int(doc.idealWidth()) + 8, max(24, int(doc.size().height()) + 6))


class AIModelResultsTable(QWidget):
    """Table showing model planning attempts.

    Visible columns:
    - Model
    - Pokusy (legal attempts sorted by score)
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
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 0)
        layout.setSpacing(0)

        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["Model", "Pokusy"])

        self.table.setStyleSheet(
            """
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
            """
        )

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setItemDelegateForColumn(1, _AttemptsRichTextDelegate(self.table))

        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)

        self.table.cellClicked.connect(self._on_cell_clicked)
        self.table.setMouseTracking(True)
        self.table.viewport().setMouseTracking(True)
        self.table.cellEntered.connect(self._on_cell_entered)
        self.table.viewport().installEventFilter(self)
        self.table.viewport().setCursor(Qt.CursorShape.ArrowCursor)

        self.table.setMinimumHeight(0)
        self.table.setMaximumHeight(250)
        layout.addWidget(self.table)
        self.table.setRowCount(0)

    def _on_cell_entered(self, _row: int, column: int) -> None:
        if column == 0:
            self.table.viewport().setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            self.table.viewport().setCursor(Qt.CursorShape.ArrowCursor)

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if obj is self.table.viewport() and event.type() == QEvent.Type.Leave:
            self.table.viewport().setCursor(Qt.CursorShape.ArrowCursor)
        return super().eventFilter(obj, event)

    def set_results(self, results: list[dict[str, Any]]) -> None:
        if not results:
            self.clear_results()
            return

        mapped: dict[str, dict[str, Any]] = {}
        for result in results:
            model_id = result.get("model")
            if model_id is None:
                continue
            existing = self._results_by_model.get(model_id, {})
            merged_result = dict(existing)
            merged_result.update(result)
            mapped[model_id] = merged_result

        self._results_by_model = mapped
        self._render_results()

    def initialize_models(self, models: list[dict[str, Any]]) -> None:
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
                "attempts_display": "",
                "best_attempt_score": None,
                "order": order_index,
            }

        self._results_by_model = pending_entries
        self._render_results()

    def update_result(self, result: dict[str, Any]) -> None:
        model_id = result.get("model") or result.get("id")
        if not model_id:
            if result.get("status") == "timer":
                return
            log.warning("Ignoring partial result without model id: %s", result)
            return

        existing = self._results_by_model.get(model_id, {})
        merged = {**existing, **result}
        self._results_by_model[model_id] = merged
        self._render_results()

    def remove_model(self, model_id: str) -> None:
        """Remove model row from table if present."""
        key = str(model_id or "").strip()
        if not key:
            return
        if key not in self._results_by_model:
            return
        self._results_by_model.pop(key, None)
        self._render_results()

    @staticmethod
    def _coerce_int(value: Any) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _sort_score(self, entry: dict[str, Any]) -> int:
        best_attempt = self._coerce_int(entry.get("best_attempt_score"))
        if best_attempt is not None:
            return best_attempt
        final_score = self._coerce_int(entry.get("score"))
        return final_score if final_score is not None else -1

    def _render_results(self) -> None:
        if not self._results_by_model:
            self.table.setRowCount(0)
            self.table.setMinimumHeight(0)
            self.results = []
            return

        records = list(self._results_by_model.values())

        def sort_key(r: dict[str, Any]) -> tuple[int, int, int, str]:
            status = str(r.get("status") or "error").lower()
            if status in {"ready", "pending", "tool_use", "tool_result", "retry"}:
                return (1, r.get("order", 0), 0, str(r.get("model_name", "")))

            status_priority = {
                "ok": 0,
                "invalid": 1,
                "parse_error": 2,
                "error": 3,
            }.get(status, 4)
            score_value = self._sort_score(r)
            return (0, -score_value, status_priority, str(r.get("model_name", "")))

        sorted_results = sorted(records, key=sort_key)

        self.results = sorted_results
        self.table.setRowCount(len(sorted_results))
        self.table.setMinimumHeight(180)

        for idx, result in enumerate(sorted_results):
            is_winner = idx == 0 and bool(result.get("judge_valid", False))
            self._populate_row(idx, result, is_winner=is_winner)

        self.table.resizeRowsToContents()

        has_pending = any(
            str(entry.get("status") or "").lower()
            in {"pending", "tool_use", "tool_result", "retry"}
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

    def _attempts_text(self, result: dict[str, Any], status: str) -> str:
        attempts_display = str(result.get("attempts_display") or "").strip()
        if attempts_display:
            return attempts_display

        words = result.get("words") or []
        score = self._coerce_int(result.get("score"))
        if status == "ok" and words:
            words_text = "+".join(str(w) for w in words)
            if score is not None and score >= 0:
                return f"{words_text} ({score})"
            return words_text

        if status == "ready":
            return ""

        if status in {"pending", "tool_use", "tool_result", "retry"}:
            return ""

        error = str(result.get("error") or "").strip()
        if error:
            if len(error) > 90:
                return f"⚠️ {error[:90]}..."
            return f"⚠️ {error}"
        return "—"

    def _populate_row(self, row: int, result: dict[str, Any], is_winner: bool) -> None:
        model_name = str(result.get("model_name", result.get("model", "Unknown")))
        status = str(result.get("status", "error") or "error").lower()
        pending_statuses = {"pending", "tool_use", "tool_result", "retry"}

        if is_winner:
            bg_color = QColor(34, 139, 34)
            text_color = QColor(255, 255, 255)
            font_bold = True
        elif status in {"pending", "ready", "tool_use", "tool_result", "retry"}:
            bg_color = QColor(40, 45, 70)
            text_color = QColor(190, 200, 235)
            font_bold = False
        elif status == "ok" and result.get("judge_valid"):
            bg_color = QColor(28, 100, 28)
            text_color = QColor(144, 238, 144)
            font_bold = False
        elif status in {"parse_error", "exception"}:
            bg_color = QColor(48, 48, 48)
            text_color = QColor(225, 225, 225)
            font_bold = False
        elif status in {"error", "timeout", "invalid"}:
            bg_color = QColor(48, 48, 48)
            text_color = QColor(225, 225, 225)
            font_bold = False
        else:
            bg_color = QColor(50, 50, 50)
            text_color = QColor(210, 210, 210)
            font_bold = False

        model_label = model_name
        if status in pending_statuses:
            model_label = f"{self._pending_frame()} {model_name}"

        model_item = QTableWidgetItem(model_label)
        model_item.setBackground(bg_color)
        model_item.setForeground(text_color)
        if font_bold:
            font = model_item.font()
            font.setBold(True)
            model_item.setFont(font)
        self.table.setItem(row, 0, model_item)

        attempts_text = self._attempts_text(result, status)
        attempts_html_raw = str(result.get("attempts_html") or "").strip()
        attempts_item = QTableWidgetItem(attempts_text)
        attempts_item.setBackground(bg_color)
        attempts_item.setForeground(QColor(255, 255, 255))
        if attempts_html_raw:
            attempts_item.setData(Qt.ItemDataRole.UserRole, attempts_html_raw)
        attempts_item.setToolTip(str(result.get("error") or attempts_text))
        if font_bold:
            font = attempts_item.font()
            font.setBold(True)
            attempts_item.setFont(font)
        self.table.setItem(row, 1, attempts_item)

    def _pending_frame(self) -> str:
        return _PENDING_FRAMES[self._pending_phase % len(_PENDING_FRAMES)]

    def _on_pending_tick(self) -> None:
        pending_statuses = {"pending", "tool_use", "tool_result", "retry"}
        if not any(str(r.get("status") or "").lower() in pending_statuses for r in self.results):
            if self._pending_timer.isActive():
                self._pending_timer.stop()
            self._pending_phase = 0
            return

        self._pending_phase = (self._pending_phase + 1) % len(_PENDING_FRAMES)
        frame = self._pending_frame()
        for idx, result in enumerate(self.results):
            if str(result.get("status") or "").lower() not in pending_statuses:
                continue
            model_item = self.table.item(idx, 0)
            if model_item is not None:
                model_name = str(result.get("model_name", result.get("model", "Unknown")))
                model_item.setText(f"{frame} {model_name}")

    def clear_results(self) -> None:
        self.table.setRowCount(0)
        self.table.setMinimumHeight(0)
        self.results = []
        self._results_by_model = {}
        if self._pending_timer.isActive():
            self._pending_timer.stop()
        self._pending_phase = 0

    def _on_cell_clicked(self, row: int, _column: int) -> None:
        if 0 <= row < len(self.results):
            result = self.results[row]
            status = str(result.get("status") or "").lower()
            model_id = str(result.get("model") or "")
            model_name = str(result.get("model_name") or model_id)

            if model_id.startswith("agent:"):
                self.agent_row_clicked.emit(model_id, model_name)
                return

            if status in {"pending", "ready", "tool_use", "tool_result", "retry"}:
                return
            dialog = ResponseDetailDialog(result, parent=self)
            dialog.exec()
