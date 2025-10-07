"""AI Configuration Dialog for selecting models."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from PySide6.QtCore import Qt, QThread, QObject, Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QCheckBox, QSpinBox, QScrollArea, QWidget, QMessageBox,
    QProgressBar, QFrame, QComboBox, QLineEdit,
)

from ..ai.openrouter import OpenRouterClient, calculate_estimated_cost

log = logging.getLogger("scrabgpt.ui")


class ModelFetchWorker(QObject):
    """Worker to fetch models from OpenRouter in background."""
    
    finished = Signal(list)
    failed = Signal(str)
    
    def __init__(self, api_key: str, order: str) -> None:
        super().__init__()
        self.api_key = api_key
        self.order = order
    
    def run(self) -> None:
        try:
            async def fetch() -> list[dict[str, Any]]:
                client = OpenRouterClient(self.api_key)
                models = await client.fetch_models(order=self.order)
                await client.close()
                return models
            
            models = asyncio.run(fetch())
            self.finished.emit(models)
        except Exception as e:
            log.exception("Failed to fetch models: %s", e)
            self.failed.emit(str(e))


class AIConfigDialog(QDialog):
    """Dialog for configuring AI models."""
    
    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        default_tokens: int = 3600,
        lock_default: bool = False,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Nastaviť AI Modely (Top Weekly)")
        self.setModal(True)
        self.resize(950, 650)
        
        self.models: list[dict[str, Any]] = []
        self.sorted_models: list[dict[str, Any]] = []
        self.filtered_models: list[dict[str, Any]] = []
        self.model_checkboxes: dict[str, QCheckBox] = {}
        self.selected_models: list[dict[str, Any]] = []
        self.max_selection = 10
        self.current_order = "week"
        self.pending_order = "week"
        self.sort_combo: QComboBox | None = None
        self.free_models_label: QLabel | None = None
        self.select_free_btn: QPushButton | None = None
        self.total_tokens_label: QLabel | None = None
        self._default_shared_tokens = self._clamp_shared_tokens(default_tokens)
        self.search_edit: QLineEdit | None = None
        self._search_text: str = ""
        self._selection_state: dict[str, bool] = {}
        self.sort_options: list[tuple[str, str]] = [
            ("Top Weekly", "top_weekly"),
            ("Newest", "newest"),
            ("Pricing: Low to High", "price_low"),
            ("Pricing: High to Low", "price_high"),
            ("Context: High to Low", "context_high"),
            ("Throughput: High to Low", "throughput_high"),
            ("Latency: Low to High", "latency_low"),
        ]

        self._setup_ui()
        self._load_models(order=self.current_order)
    
    def _setup_ui(self) -> None:
        self.setStyleSheet(
            "QDialog { background-color: #0f1a12; color: #e8f5e9; }"
            "QLabel { color: #e8f5e9; }"
            "QScrollArea { background-color: #0f1a12; }"
        )

        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(12, 12, 12, 12)

        controls_layout = QHBoxLayout()
        controls_layout.setSpacing(8)

        sort_caption = QLabel("Zoradenie:")
        sort_caption.setStyleSheet("font-size: 13px; font-weight: bold; color: #9ad0a2;")
        controls_layout.addWidget(sort_caption)

        self.sort_combo = QComboBox()
        for text, key in self.sort_options:
            self.sort_combo.addItem(text, key)
        self.sort_combo.setCurrentIndex(0)
        self.sort_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        self.sort_combo.setStyleSheet(
            "QComboBox { "
            "font-size: 13px; font-weight: bold; color: #e6f7eb; padding: 6px 12px; "
            "background: #173422; border: 1px solid #2f5c39; border-radius: 6px;"
            "} "
            "QComboBox::drop-down { border: none; width: 24px; } "
            "QComboBox::down-arrow { image: none; } "
            "QComboBox QAbstractItemView { font-size: 13px; background: #0f1a12; color: #e6f7eb; selection-background-color: #295c33; selection-color: #e6f7eb; border: 1px solid #2f5c39; }"
        )
        self.sort_combo.currentIndexChanged.connect(self._on_sort_changed)
        controls_layout.addWidget(self.sort_combo)
        controls_layout.addStretch()

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Hľadaj model…")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setStyleSheet(
            "QLineEdit { "
            "background: #080b08; color: #e6f7eb; border: 1px solid #2f5c39; "
            "border-radius: 6px; padding: 6px 10px; min-width: 220px; font-size: 12px; "
            "} "
            "QLineEdit:focus { border-color: #4caf50; }"
        )
        self.search_edit.textChanged.connect(self._on_search_changed)
        controls_layout.addWidget(self.search_edit)

        layout.addLayout(controls_layout)

        info = QLabel("Vyber modely pre konkurenčné hranie (max. 10). Najlepší ťah (najvyššie skóre) sa použije.")
        info.setWordWrap(True)
        info.setStyleSheet(
            "padding: 10px 12px; background: #1b3822; border-radius: 6px; "
            "color: #e6f7eb; font-size: 13px; font-weight: bold; border: 1px solid #2f5c39;"
        )
        layout.addWidget(info)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setTextVisible(False)
        self.progress.setStyleSheet(
            "QProgressBar { background: #132418; border: 1px solid #2f5c39; border-radius: 6px; }"
            "QProgressBar::chunk { background-color: #4caf50; border-radius: 6px; }"
        )
        layout.addWidget(self.progress)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            "QScrollArea { border: 1px solid #264b30; border-radius: 6px; background: #0f1a12; }"
        )

        self.models_container = QWidget()
        self.models_layout = QVBoxLayout(self.models_container)
        self.models_layout.setSpacing(6)
        self.models_layout.setContentsMargins(8, 8, 8, 8)
        self.models_container.setStyleSheet("background-color: #0f1a12;")
        scroll.setWidget(self.models_container)
        
        layout.addWidget(scroll, stretch=1)

        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        separator.setStyleSheet("background: #2f5c39;")
        layout.addWidget(separator)

        self.cost_label = QLabel("Vyber aspoň jeden model")
        self.cost_label.setStyleSheet(
            "padding: 10px; background: #2f2415; border-radius: 6px; "
            "font-size: 13px; font-weight: bold; color: #f5e6c4; border: 2px solid #d8a02f;"
        )
        self.cost_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.cost_label)

        button_layout = QHBoxLayout()
        button_layout.setSpacing(8)

        self.cancel_btn = QPushButton("✗ Zrušiť")
        self.cancel_btn.clicked.connect(self.reject)
        self.cancel_btn.setStyleSheet(
            "QPushButton { padding: 8px 16px; font-size: 12px; border-radius: 6px; "
            "background-color: #182c1d; color: #b6e0bd; border: 1px solid #2f5c39; }"
            "QPushButton:hover { background-color: #213c28; }"
            "QPushButton:pressed { background-color: #112015; }"
        )
        button_layout.addWidget(self.cancel_btn)

        # Total tokens cost calculation (yellow label)
        self.total_tokens_label = QLabel("Celkový max tokenov: 0")
        self.total_tokens_label.setStyleSheet(
            "font-size: 13px; font-weight: bold; color: #ffd54f; "
            "padding: 6px 12px; background: #3d2a0f; border: 1px solid #8a6a4a; border-radius: 4px;"
        )
        self.total_tokens_label.setToolTip(
            "Celkový počet tokenov, ktoré budú použité pri volaní všetkých vybraných modelov súčasne\\n"
            "(počet modelov × max tokenov na ťah)"
        )
        button_layout.addWidget(self.total_tokens_label)

        button_layout.addStretch()

        self.free_models_label = QLabel("Modelov s free volaniami: 0")
        self.free_models_label.setStyleSheet(
            "font-size: 12px; font-weight: bold; color: #9ad0a2;"
        )
        button_layout.addWidget(self.free_models_label)

        self.select_free_btn = QPushButton("Vybrať free modely")
        self.select_free_btn.setEnabled(False)
        self.select_free_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.select_free_btn.setStyleSheet(
            "QPushButton { "
            "background-color: #2f8f46; color: #0b1c00; font-weight: bold; "
            "padding: 8px 16px; border-radius: 6px; font-size: 12px; border: 1px solid #246c34; "
            "} "
            "QPushButton:hover { background-color: #3fa75a; } "
            "QPushButton:pressed { background-color: #236a34; color: #d7f4dd; } "
            "QPushButton:disabled { background-color: #1f3323; color: #4f6f55; border-color: #1f3323; }"
        )
        self.select_free_btn.clicked.connect(self._select_free_models)
        button_layout.addWidget(self.select_free_btn)

        self.ok_btn = QPushButton("✓ Použiť vybrané modely")
        self.ok_btn.clicked.connect(self._on_ok)
        self.ok_btn.setEnabled(False)
        self.ok_btn.setStyleSheet(
            "QPushButton { "
            "background-color: #4caf50; color: #0b1c00; font-weight: bold; "
            "padding: 8px 18px; border-radius: 6px; font-size: 12px; border: 1px solid #3f9143; "
            "} "
            "QPushButton:hover { background-color: #5cc75f; } "
            "QPushButton:pressed { background-color: #3f9143; color: #d7f4dd; } "
            "QPushButton:disabled { background-color: #1f3323; color: #4f6f55; border-color: #1f3323; }"
        )
        button_layout.addWidget(self.ok_btn)

        layout.addLayout(button_layout)

    def _current_sort_key(self) -> str:
        """Return the currently selected sort key."""

        if self.sort_combo is None:
            return "top_weekly"

        data = self.sort_combo.currentData(Qt.ItemDataRole.UserRole)
        return data if isinstance(data, str) else "top_weekly"

    def _on_sort_changed(self, _index: int) -> None:
        """Handle sort changes from the combo box."""

        sort_key = self._current_sort_key()

        if sort_key == "top_weekly":
            if self.current_order != "week":
                self._load_models(order="week")
                return
        elif sort_key == "newest":
            if self.current_order != "created":
                self._load_models(order="created")
                return

        self._apply_sort(sort_key)

    def _on_search_changed(self, text: str) -> None:
        """Filter model list as the user edits the search box."""

        cleaned = text.strip()
        if cleaned == self._search_text:
            return
        self._search_text = cleaned
        self._refresh_model_list()

    def _apply_sort(self, sort_key: str) -> None:
        """Sort models according to the selected strategy and refresh UI."""

        if not self.models:
            self.sorted_models = []
            self._refresh_model_list()
            return

        models = list(self.models)

        if sort_key == "price_low":
            models.sort(
                key=lambda m: (
                    float(m.get("prompt_price", 0) or 0) + float(m.get("completion_price", 0) or 0),
                    m.get("name", m.get("id", "")),
                )
            )
        elif sort_key == "price_high":
            models.sort(
                key=lambda m: (
                    float(m.get("prompt_price", 0) or 0) + float(m.get("completion_price", 0) or 0),
                    m.get("name", m.get("id", "")),
                ),
                reverse=True,
            )
        elif sort_key == "context_high":
            models.sort(
                key=lambda m: int(m.get("context_length", 0) or 0),
                reverse=True,
            )
        elif sort_key == "throughput_high":
            models.sort(
                key=lambda m: self._get_metric(m, "throughput", default=0.0),
                reverse=True,
            )
        elif sort_key == "latency_low":
            models.sort(
                key=lambda m: self._get_metric(m, "latency", default=float("inf")),
            )
        else:
            # 'top_weekly' and 'newest' keep API ordering
            pass

        self.sorted_models = models
        self._refresh_model_list()

    def _refresh_model_list(self) -> None:
        """Apply search filter to the sorted models and refresh the UI."""

        base_models = self.sorted_models if self.sorted_models else list(self.models)

        if self._search_text:
            needle = self._search_text.casefold()
            filtered = [
                model for model in base_models if self._matches_search(model, needle)
            ]
        else:
            filtered = base_models

        self.filtered_models = filtered
        self._populate_models(filtered)

    def _load_models(self, *, order: str | None = None) -> None:
        """Load models from OpenRouter in background."""
        import os
        api_key = os.getenv("OPENROUTER_API_KEY", "")

        if not api_key:
            QMessageBox.warning(
                self,
                "API Key",
                "OPENROUTER_API_KEY nie je nastavený.\n"
                "Pridaj ho do .env súboru.",
            )
            self.reject()
            return

        order_to_use = order or self.current_order
        self.pending_order = order_to_use

        if self.sort_combo is not None:
            self.sort_combo.setEnabled(False)

        self.progress.show()

        self.worker_thread = QThread()
        self.worker = ModelFetchWorker(api_key, order_to_use)
        self.worker.moveToThread(self.worker_thread)

        self.worker_thread.started.connect(self.worker.run)
        self.worker.finished.connect(self._on_models_loaded)
        self.worker.failed.connect(self._on_models_failed)
        self.worker.finished.connect(self.worker_thread.quit)
        self.worker.failed.connect(self.worker_thread.quit)
        
        self.worker_thread.start()
    
    def _on_models_loaded(self, models: list[dict[str, Any]]) -> None:
        """Handle loaded models."""
        self.progress.hide()
        if self.sort_combo is not None:
            self.sort_combo.setEnabled(True)

        if not models:
            QMessageBox.warning(self, "Modely", "Žiadne modely neboli načítané.")
            self.reject()
            return

        # Show all models, sorted by weekly trending (already sorted by API with order=week)
        self.current_order = self.pending_order
        previous_state = self._selection_state
        self.models = models
        self._selection_state = {
            model.get("id", ""): previous_state.get(model.get("id", ""), False)
            for model in models
            if model.get("id")
        }
        # Token limit is now managed in settings, not dynamically updated
        current_sort_key = self._current_sort_key()
        self._apply_sort(current_sort_key)

    def _on_models_failed(self, error: str) -> None:
        """Handle model loading failure."""
        self.progress.hide()
        if self.sort_combo is not None:
            self.sort_combo.setEnabled(True)
        QMessageBox.critical(
            self,
            "Chyba",
            f"Nepodarilo sa načítať modely:\n{error}",
        )
        self.reject()
    
    def _populate_models(self, models: list[dict[str, Any]]) -> None:
        """Populate UI with model checkboxes - one line per model."""

        for model_id, checkbox in self.model_checkboxes.items():
            self._selection_state[model_id] = checkbox.isChecked()

        while self.models_layout.count():
            item = self.models_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        self.model_checkboxes.clear()

        if not models:
            empty_label = QLabel("Žiadne modely zodpovedajú hľadaniu.")
            empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty_label.setStyleSheet(
                "color: #8fa6a0; font-size: 12px; padding: 12px;"
            )
            self.models_layout.addWidget(empty_label)
            self.models_layout.addStretch()
            self._update_free_models_indicator()
            self._update_cost()
            return

        for model in models:
            model_id = model["id"]
            model_name = model.get("name", model_id)
            context_length = int(model.get("context_length", 0) or 0)
            prompt_price = float(model.get("prompt_price", 0) or 0)
            completion_price = float(model.get("completion_price", 0) or 0)

            frame = QFrame()
            frame.setFrameShape(QFrame.Shape.StyledPanel)
            frame.setStyleSheet(
                "QFrame { "
                "border: 1px solid #2f5c39; border-radius: 6px; "
                "background: #080b08; padding: 10px; "
                "} "
                "QFrame:hover { border-color: #4caf50; background: #111611; }"
            )

            frame_layout = QHBoxLayout(frame)
            frame_layout.setSpacing(12)
            frame_layout.setContentsMargins(10, 8, 10, 8)

            checkbox = QCheckBox(self._format_checkbox_text(model_name, context_length))
            checkbox.setStyleSheet(
                "QCheckBox { "
                "font-size: 13px; font-weight: bold; color: #e6f7eb; "
                "} "
                "QCheckBox::indicator { width: 18px; height: 18px; }"
                "QCheckBox::indicator:unchecked { border: 1px solid #4caf50; background: #0f1a12; }"
                "QCheckBox::indicator:checked { border: 1px solid #4caf50; background: #4caf50; }"
            )
            checkbox.stateChanged.connect(lambda state, mid=model_id: self._on_checkbox_changed(mid, state))
            self.model_checkboxes[model_id] = checkbox
            frame_layout.addWidget(checkbox, stretch=1)

            price_label = QLabel(self._format_price_label(prompt_price, completion_price))
            price_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            price_label.setStyleSheet(
                "font-size: 11px; font-weight: bold; color: #9ad0a2;"
            )

            frame_layout.addWidget(price_label, alignment=Qt.AlignmentFlag.AlignRight)

            if self._selection_state.get(model_id, False):
                checkbox.blockSignals(True)
                checkbox.setChecked(True)
                checkbox.blockSignals(False)
            else:
                self._selection_state.setdefault(model_id, False)

            self.models_layout.addWidget(frame)

        self.models_layout.addStretch()
        self._update_free_models_indicator()
        self._update_cost()
    
    @staticmethod
    def _format_checkbox_text(model_name: str, context_length: int) -> str:
        """Return checkbox caption with bold model name and context length."""

        context = AIConfigDialog._format_context_length(context_length)
        if context:
            return f"{model_name} ({context} context)"
        return model_name

    @staticmethod
    def _matches_search(model: dict[str, Any], needle: str) -> bool:
        """Return True if the model metadata matches the search needle."""

        fields = ("name", "id", "provider", "description")
        for key in fields:
            value = model.get(key)
            if isinstance(value, str) and needle in value.casefold():
                return True
        tags = model.get("tags")
        if isinstance(tags, (list, tuple)):
            for tag in tags:
                if isinstance(tag, str) and needle in tag.casefold():
                    return True
        return False

    @staticmethod
    def _clamp_shared_tokens(value: int) -> int:
        """Clamp shared token limit to supported widget range."""

        return max(500, min(20000, value))

    @staticmethod
    def _format_context_length(context_length: int) -> str:
        """Format context length in tokens into a compact string."""

        if context_length <= 0:
            return "n/a"
        if context_length >= 1_000_000:
            return f"{context_length / 1_000_000:.1f}M"
        if context_length >= 1_000:
            return f"{context_length // 1_000}K"
        return str(context_length)

    @staticmethod
    def _format_price_label(prompt_price: float, completion_price: float) -> str:
        """Create a pricing summary shown next to the token spinbox."""

        prompt_per_k = prompt_price * 1000
        completion_per_k = completion_price * 1000

        if prompt_price == 0 and completion_price == 0:
            return "Tokeny | zadarmo"

        return (
            "Tokeny | "
            f"${prompt_per_k:.2f}/1k prompt | "
            f"${completion_per_k:.2f}/1k completion"
        )

    @staticmethod
    def _get_metric(model: dict[str, Any], metric: str, *, default: float) -> float:
        """Safely extract numeric metrics from various model metadata buckets."""

        candidates = [
            model.get(metric),
            model.get("stats", {}).get(metric) if isinstance(model.get("stats"), dict) else None,
            model.get("metrics", {}).get(metric) if isinstance(model.get("metrics"), dict) else None,
            model.get("meta", {}).get(metric) if isinstance(model.get("meta"), dict) else None,
            model.get("performance", {}).get(metric) if isinstance(model.get("performance"), dict) else None,
        ]

        for value in candidates:
            if isinstance(value, (int, float)):
                return float(value)

        return default

    def _update_free_models_indicator(self) -> None:
        """Refresh the badge that shows how many free models are available."""

        if self.free_models_label is None or self.select_free_btn is None:
            return

        free_count = sum(1 for model in self.models if self._is_free_model(model))
        self.free_models_label.setText(f"Modelov s free volaniami: {free_count}")
        self.select_free_btn.setEnabled(free_count > 0)

    @staticmethod
    def _is_free_model(model: dict[str, Any]) -> bool:
        """Return True when both prompt and completion prices are zero."""

        prompt_price = float(model.get("prompt_price", 0) or 0)
        completion_price = float(model.get("completion_price", 0) or 0)
        return prompt_price == 0 and completion_price == 0

    def _select_free_models(self) -> None:
        """Select every free model, respecting the maximum selection cap."""

        search_space = self.filtered_models or self.sorted_models or self.models
        free_models = [
            model for model in search_space if self._is_free_model(model)
        ] or [
            model for model in self.models if self._is_free_model(model)
        ]

        if not free_models:
            return

        for model in self.models:
            self._selection_state[model["id"]] = False

        for checkbox in self.model_checkboxes.values():
            checkbox.blockSignals(True)
            checkbox.setChecked(False)
            checkbox.blockSignals(False)

        for model in free_models[: self.max_selection]:
            checkbox = self.model_checkboxes.get(model["id"])
            if checkbox is None:
                self._selection_state[model["id"]] = True
                continue
            checkbox.blockSignals(True)
            checkbox.setChecked(True)
            checkbox.blockSignals(False)
            self._selection_state[model["id"]] = True

        self._update_cost()

        if len(free_models) > self.max_selection:
            QMessageBox.information(
                self,
                "Limit dosiahnutý",
                (
                    f"Vybralo sa {self.max_selection} free modelov z {len(free_models)} dostupných.\n"
                    "Vyber menej modelov alebo uprav limit."
                ),
            )

    def _on_shared_tokens_changed(self, _value: int) -> None:
        """Track user override and recompute cost preview."""

        if self._updating_shared_tokens:
            return

        self._shared_tokens_customized = True
        self._update_shared_tokens_caption()
        self._update_cost()

    def _shared_tokens_value(self) -> int:
        """Return the token cap shared across selected models."""

        if self.shared_tokens_spinbox is None:
            return self._default_shared_tokens
        return self.shared_tokens_spinbox.value()

    def _set_shared_tokens_value(self, value: int) -> None:
        """Update the shared spinbox without triggering customization flags."""

        if self.shared_tokens_spinbox is None:
            return

        self._updating_shared_tokens = True
        self.shared_tokens_spinbox.setValue(value)
        self._updating_shared_tokens = False
        self._update_shared_tokens_caption()

    def _update_shared_tokens_caption(self) -> None:
        """Refresh the caption showing the current shared token limit."""

        if self.shared_tokens_label is None:
            return
        self.shared_tokens_label.setText("Maximálne tokenov na ťah:")
        self.shared_tokens_label.setToolTip(
            f"Aktuálny limit: {self._shared_tokens_value()} tokenov"
        )

    def _maybe_update_shared_tokens_default(self) -> None:
        """Apply a context-aware default when the user has not changed it yet."""

        if self._shared_tokens_customized:
            return

        recommended = self._recommend_shared_tokens()
        self._set_shared_tokens_value(recommended)
        self._update_cost()

    def _recommend_shared_tokens(self) -> int:
        """Suggest a reasonable shared token cap from loaded model contexts."""

        contexts = [
            int(model.get("context_length", 0) or 0)
            for model in self.models
            if int(model.get("context_length", 0) or 0) > 0
        ]

        if not contexts:
            return max(500, min(10000, self._shared_tokens_value()))

        min_context = min(contexts)
        recommended = max(500, min_context // 3)
        if recommended == 0:
            recommended = 5000

        return max(500, min(10000, recommended))

    def _on_checkbox_changed(self, model_id: str, state: int) -> None:
        """Handle checkbox state change with max selection limit."""
        checkbox = self.model_checkboxes.get(model_id)
        if checkbox is None:
            return

        if state == Qt.CheckState.Checked.value:
            current_selected = sum(1 for value in self._selection_state.values() if value)
            if not self._selection_state.get(model_id, False):
                current_selected += 1

            if current_selected > self.max_selection:
                checkbox.blockSignals(True)
                checkbox.setChecked(False)
                checkbox.blockSignals(False)
                self._selection_state[model_id] = False
                QMessageBox.warning(
                    self,
                    "Limit dosiahnutý",
                    f"Môžeš vybrať maximálne {self.max_selection} modelov.",
                )
                self._update_cost()
                return

        self._selection_state[model_id] = checkbox.isChecked()
        self._update_cost()
    
    def _update_cost(self) -> None:
        """Update estimated cost based on selected models."""
        selected = []
        
        shared_tokens = self._shared_tokens_value()

        for model in self.models:
            model_id = model["id"]
            if not self._selection_state.get(model_id, False):
                continue
            model_copy = model.copy()
            model_copy["max_tokens"] = shared_tokens
            selected.append(model_copy)
        
        self.ok_btn.setEnabled(len(selected) > 0)
        
        if not selected:
            self.cost_label.setText("⚠️  Vyber aspoň jeden model")
            self.cost_label.setStyleSheet(
                "padding: 10px; background: #2f2415; border-radius: 6px; "
                "font-size: 13px; font-weight: bold; color: #f5e6c4; border: 2px solid #d8a02f;"
            )
            return
        
        prompt_tokens = 2000
        max_completion = max(m["max_tokens"] for m in selected)
        
        total_cost = calculate_estimated_cost(selected, prompt_tokens, max_completion)
        
        if total_cost >= 0.01:
            cost_str = f"${total_cost:.4f}"
        elif total_cost >= 0.0001:
            cost_str = f"${total_cost:.6f}"
        else:
            cost_str = f"${total_cost:.8f}"
        
        self.cost_label.setText(
            f"✓ {len(selected)} modelov vybraných  |  "
            f"💰 Maximálna cena za ťah: {cost_str}"
        )
        self.cost_label.setStyleSheet(
            "padding: 10px; background: #173422; border-radius: 6px; "
            "font-size: 13px; font-weight: bold; color: #9ad0a2; border: 2px solid #4caf50;"
        )
    
    def _on_ok(self) -> None:
        """Save selected models and close."""
        self.selected_models = []
        
        shared_tokens = self._shared_tokens_value()

        for model in self.models:
            model_id = model["id"]
            checkbox = self.model_checkboxes.get(model_id)

            if checkbox and checkbox.isChecked():
                model_copy = model.copy()
                model_copy["max_tokens"] = shared_tokens
                self.selected_models.append(model_copy)
        
        if not self.selected_models:
            QMessageBox.warning(self, "Modely", "Vyber aspoň jeden model.")
            return
        
        self.accept()
    
    def get_selected_models(self) -> list[dict[str, Any]]:
        """Get selected models with their configurations."""
        return self.selected_models

    def get_shared_tokens_value(self) -> int:
        """Return the shared max token setting for selected models."""
        return self._default_shared_tokens
