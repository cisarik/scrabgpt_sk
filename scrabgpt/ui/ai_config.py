"""AI Configuration Dialog for selecting models."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Callable

from PySide6.QtCore import Qt, QThread, QObject, Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QCheckBox, QScrollArea, QWidget, QMessageBox,
    QProgressBar, QFrame, QComboBox, QLineEdit, QInputDialog,
)

from ..ai.openrouter import OpenRouterClient, calculate_estimated_cost
from ..core.team_config import TeamConfig, get_team_manager

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
        current_team_name: str | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Nastaviť OpenRouter team")
        self.setModal(True)
        self.resize(950, 700)
        
        self.models: list[dict[str, Any]] = []
        self.base_models: list[dict[str, Any]] = []
        self.pinned_models: list[dict[str, Any]] = []
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
        self._default_shared_tokens = self._clamp_shared_tokens(default_tokens)
        self.search_edit: QLineEdit | None = None
        self._search_text: str = ""
        self._selection_state: dict[str, bool] = {}
        self.team_manager = get_team_manager()
        self.current_team_name = current_team_name or self.team_manager.load_active_team("openrouter")
        self.team_combo: QComboBox | None = None
        self.ok_btn: QPushButton | None = None
        self.sort_options: list[tuple[str, str]] = [
            ("Top Weekly", "top_weekly"),
            ("Newest", "newest"),
            ("Pricing: Low to High", "price_low"),
            ("Pricing: High to Low", "price_high"),
            ("Context: High to Low", "context_high"),
            ("Throughput: High to Low", "throughput_high"),
            ("Latency: Low to High", "latency_low"),
        ]
        self._sort_strategies: dict[str, tuple[Callable[[dict[str, Any]], Any], bool]] = {
            "price_low": (self._sort_key_total_price, False),
            "price_high": (self._sort_key_total_price, True),
            "context_high": (self._sort_key_context_length, True),
            "throughput_high": (self._sort_key_throughput, True),
            "latency_low": (self._sort_key_latency, False),
        }

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
        
        # Team selector
        team_label = QLabel("Team:")
        team_label.setStyleSheet("font-size: 13px; font-weight: bold; color: #9ad0a2;")
        controls_layout.addWidget(team_label)
        
        self.team_combo = QComboBox()
        self.team_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        self.team_combo.setStyleSheet(
            "QComboBox { "
            "font-size: 13px; font-weight: bold; color: #e6f7eb; padding: 6px 12px; "
            "background: #000000; border: 1px solid #2f5c39; border-radius: 6px;"
            "} "
            "QComboBox:hover { border-color: #4caf50; background: #0a0a0a; } "
            "QComboBox:focus { border-color: #4caf50; } "
            "QComboBox::drop-down { border: none; width: 24px; } "
            "QComboBox QAbstractItemView { "
            "font-size: 13px; background: #000000; color: #e6f7eb; "
            "selection-background-color: #295c33; selection-color: #e6f7eb; "
            "border: 1px solid #2f5c39; "
            "}"
        )
        controls_layout.addWidget(self.team_combo)
        
        # New/Rename team buttons
        new_team_btn = QPushButton("+ Nový")
        new_team_btn.setStyleSheet(self._small_button_style())
        new_team_btn.clicked.connect(self._create_new_team)
        controls_layout.addWidget(new_team_btn)
        
        rename_team_btn = QPushButton("✎ Premenovať")
        rename_team_btn.setStyleSheet(self._small_button_style())
        rename_team_btn.clicked.connect(self._rename_team)
        controls_layout.addWidget(rename_team_btn)
        
        delete_team_btn = QPushButton("🗑️ Zmazať")
        delete_team_btn.setStyleSheet(self._small_button_style_danger())
        delete_team_btn.clicked.connect(self._delete_team)
        controls_layout.addWidget(delete_team_btn)

        sort_caption = QLabel("Zoradenie:")
        sort_caption.setStyleSheet("font-size: 13px; font-weight: bold; color: #9ad0a2; margin-left: 16px;")
        controls_layout.addWidget(sort_caption)

        self.sort_combo = QComboBox()
        for text, key in self.sort_options:
            self.sort_combo.addItem(text, key)
        self.sort_combo.setCurrentIndex(0)
        self.sort_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        self.sort_combo.setStyleSheet(
            "QComboBox { "
            "font-size: 13px; font-weight: bold; color: #e6f7eb; padding: 6px 12px; "
            "background: #000000; border: 1px solid #2f5c39; border-radius: 6px;"
            "} "
            "QComboBox:hover { border-color: #4caf50; background: #0a0a0a; } "
            "QComboBox:focus { border-color: #4caf50; } "
            "QComboBox::drop-down { border: none; width: 24px; } "
            "QComboBox::down-arrow { image: none; } "
            "QComboBox QAbstractItemView { font-size: 13px; background: #000000; color: #e6f7eb; selection-background-color: #295c33; selection-color: #e6f7eb; border: 1px solid #2f5c39; }"
        )
        self.sort_combo.currentIndexChanged.connect(self._on_sort_changed)
        controls_layout.addWidget(self.sort_combo)
        controls_layout.addStretch()

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Hľadaj model…")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setStyleSheet(
            "QLineEdit { "
            "background: #000000; color: #e6f7eb; border: 1px solid #2f5c39; "
            "border-radius: 6px; padding: 6px 10px; min-width: 220px; font-size: 12px; "
            "} "
            "QLineEdit:hover { border-color: #4caf50; } "
            "QLineEdit:focus { border-color: #4caf50; background: #0a0a0a; }"
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
        
        # Now connect team combo signal and populate (after all widgets exist)
        if self.team_combo:
            self._populate_team_combo()
            self.team_combo.currentIndexChanged.connect(self._on_team_changed)

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

        if not self.base_models:
            self.sorted_models = []
            self._refresh_model_list()
            return

        models = list(self.base_models)
        sort_strategy = self._sort_strategies.get(sort_key)
        if sort_strategy is not None:
            key_func, reverse = sort_strategy
            models.sort(key=key_func, reverse=reverse)

        self.sorted_models = models
        self._refresh_model_list()

    def _refresh_model_list(self) -> None:
        """Apply search filter to the sorted models and refresh the UI."""

        base_models = self.sorted_models if self.sorted_models else list(self.base_models)
        pinned_models = list(self.pinned_models)

        if self._search_text:
            needle = self._search_text.casefold()
            filtered_base = [
                model for model in base_models if self._matches_search(model, needle)
            ]
            filtered = filtered_base
        else:
            filtered = base_models

        self.filtered_models = filtered
        self.models = base_models + pinned_models
        self._sync_selection_state()
        display_models = filtered + pinned_models
        self._populate_models(display_models)

    def _build_pinned_models(self) -> list[dict[str, Any]]:
        """Return synthetic OpenRouter auto-routing entries pinned to the list bottom."""

        # Context length is provider-dependent; show n/a in UI.
        pinned: list[dict[str, Any]] = [
            {
                "id": "openrouter/auto:floor",
                "name": "OpenRouter Auto – Floor",
                "display_name": "OpenRouter Auto · Floor (najnižšia cena)",
                "subtitle": "OpenRouter zvolí najlacnejšieho dostupného poskytovateľa pre každý dotaz.",
                "description": "Automatické smerovanie podľa ceny – ekvivalent provider.sort = 'price'.",
                "context_length": None,
                "prompt_price": None,
                "completion_price": None,
                "pricing_display": "dynamické • priorita cena",
                "tags": ["auto", "routing", "price"],
                "provider_sort": "price",
                "is_pinned": True,
            },
            {
                "id": "openrouter/auto:nitro",
                "name": "OpenRouter Auto – Nitro",
                "display_name": "OpenRouter Auto · Nitro (priorita rýchlosť)",
                "subtitle": "OpenRouter preferuje poskytovateľov s najvyšším priepustom – provider.sort = 'throughput'.",
                "description": "Automatické smerovanie podľa priepustu – vhodné pre čo najrýchlejšie odpovede.",
                "context_length": None,
                "prompt_price": None,
                "completion_price": None,
                "pricing_display": "dynamické • priorita priepustnosť",
                "tags": ["auto", "routing", "speed"],
                "provider_sort": "throughput",
                "is_pinned": True,
            },
        ]
        return pinned

    def _sync_selection_state(self) -> None:
        """Ensure selection state matches available model IDs."""

        valid_ids = {model.get("id", "") for model in self.models if model.get("id")}
        for model in self.models:
            model_id = model.get("id")
            if not model_id:
                continue
            self._selection_state.setdefault(model_id, False)
        stale_ids = [model_id for model_id in self._selection_state if model_id not in valid_ids]
        for model_id in stale_ids:
            self._selection_state.pop(model_id, None)

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
        previous_state = dict(self._selection_state)
        self.base_models = models
        self.pinned_models = self._build_pinned_models()
        self.models = self.base_models + self.pinned_models
        self._selection_state = {}
        for model in self.models:
            model_id = model.get("id")
            if not model_id:
                continue
            self._selection_state[model_id] = previous_state.get(model_id, False)
        self._sync_selection_state()
        # Token limit is now managed in settings, not dynamically updated
        
        current_sort_key = self._current_sort_key()
        self._apply_sort(current_sort_key)
        
        # Load active team's selections after models are loaded and sorted
        if self.current_team_name:
            self._load_team_selections(self.current_team_name)

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
            model_id = model.get("id")
            if not model_id:
                continue
            model_name = model.get("name", model_id)
            display_name = model.get("display_name", model_name)
            context_length = model.get("context_length")
            is_pinned = bool(model.get("is_pinned"))
            subtitle = model.get("subtitle")

            frame = QFrame()
            frame.setFrameShape(QFrame.Shape.StyledPanel)
            if is_pinned:
                frame.setStyleSheet(
                    "QFrame { "
                    "border: 1px solid #4caf50; border-radius: 6px; "
                    "background: #0d2415; padding: 10px; "
                    "} "
                    "QFrame:hover { border-color: #66d96f; background: #12301c; }"
                )
            else:
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

            checkbox = QCheckBox(self._format_checkbox_text(display_name, context_length))
            checkbox_style = (
                "QCheckBox { font-size: 13px; font-weight: bold; color: #e6f7eb; } "
                "QCheckBox::indicator { width: 18px; height: 18px; }"
                "QCheckBox::indicator:unchecked { border: 1px solid #4caf50; background: #0f1a12; }"
                "QCheckBox::indicator:checked { border: 1px solid #4caf50; background: #4caf50; }"
            )
            if is_pinned:
                checkbox_style = checkbox_style.replace("#e6f7eb", "#f3ffee")
            checkbox.setStyleSheet(checkbox_style)
            description = model.get("description")
            if description:
                checkbox.setToolTip(description)
            checkbox.stateChanged.connect(lambda state, mid=model_id: self._on_checkbox_changed(mid, state))
            self.model_checkboxes[model_id] = checkbox

            if is_pinned and subtitle:
                content_widget = QWidget()
                content_layout = QVBoxLayout(content_widget)
                content_layout.setContentsMargins(0, 0, 0, 0)
                content_layout.setSpacing(2)
                content_layout.addWidget(checkbox)
                subtitle_label = QLabel(subtitle)
                subtitle_label.setWordWrap(True)
                subtitle_label.setStyleSheet(
                    "font-size: 11px; color: #9ad0a2; margin-left: 2px;"
                )
                content_layout.addWidget(subtitle_label)
                frame_layout.addWidget(content_widget, stretch=1)
            else:
                frame_layout.addWidget(checkbox, stretch=1)

            price_label = QLabel(self._format_price_label(model))
            price_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            price_label_style = "font-size: 11px; font-weight: bold; color: #9ad0a2;"
            if is_pinned:
                price_label_style = (
                    "font-size: 11px; font-weight: bold; color: #ffd54f; "
                    "background: rgba(255, 213, 79, 0.10); padding: 4px 8px; border-radius: 4px;"
                )
                price_label.setWordWrap(True)
            price_label.setStyleSheet(price_label_style)
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
    def _format_checkbox_text(model_name: str, context_length: int | None) -> str:
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
    def _format_context_length(context_length: int | None) -> str:
        """Format context length in tokens into a compact string."""

        if not context_length or context_length <= 0:
            return "n/a"
        if context_length >= 1_000_000:
            return f"{context_length / 1_000_000:.1f}M"
        if context_length >= 1_000:
            return f"{context_length // 1_000}K"
        return str(context_length)

    @staticmethod
    def _format_price_label(model: dict[str, Any]) -> str:
        """Create a pricing summary showing completion price per token."""

        special = model.get("pricing_display")
        if isinstance(special, str) and special.strip():
            return special

        prompt_price = AIConfigDialog._safe_float(model.get("prompt_price"))
        completion_price = AIConfigDialog._safe_float(model.get("completion_price"))

        if prompt_price is None or completion_price is None:
            return "dynamické podľa poskytovateľa"

        if prompt_price == 0 and completion_price == 0:
            return "zadarmo"

        # Show full unrounded price per token (not per 1k)
        price_per_token = completion_price
        return f"${price_per_token:.10f}/token"

    @staticmethod
    def _safe_float(value: Any) -> float | None:
        """Convert a value to float, returning None when conversion is not possible."""

        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _safe_int(value: Any) -> int:
        """Convert a value to int, returning 0 on failure."""

        if value is None:
            return 0
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    def _sort_key_total_price(self, model: dict[str, Any]) -> tuple[float, str]:
        """Sort helper that prefers lower total price (prompt + completion)."""

        total_price = (self._safe_float(model.get("prompt_price")) or 0.0) + (
            self._safe_float(model.get("completion_price")) or 0.0
        )
        name = model.get("name", model.get("id", ""))
        return total_price, name

    def _sort_key_context_length(self, model: dict[str, Any]) -> int:
        """Sort helper to prioritize larger context windows."""

        return self._safe_int(model.get("context_length"))

    def _sort_key_throughput(self, model: dict[str, Any]) -> float:
        """Sort helper that prefers higher throughput metrics."""

        return self._get_metric(model, "throughput", default=0.0)

    def _sort_key_latency(self, model: dict[str, Any]) -> float:
        """Sort helper that prefers lower latency metrics."""

        return self._get_metric(model, "latency", default=float("inf"))

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

        prompt_price = AIConfigDialog._safe_float(model.get("prompt_price"))
        completion_price = AIConfigDialog._safe_float(model.get("completion_price"))
        if prompt_price is None or completion_price is None:
            return False
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
        return self._default_shared_tokens

    def _set_shared_tokens_value(self, value: int) -> None:
        """Update the shared tokens value."""
        self._default_shared_tokens = value

    def _update_shared_tokens_caption(self) -> None:
        """Refresh the caption showing the current shared token limit."""
        # No-op since we don't have a spinbox anymore
        pass

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
        if self.ok_btn is None or self.cost_label is None:
            return
        
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
        
        # Calculate max cost per move: sum of (tokens × completion_price) for each model
        total_cost = 0.0
        dynamic_pricing = False
        for model in selected:
            completion_price = self._safe_float(model.get("completion_price"))
            if completion_price is None:
                dynamic_pricing = True
                continue
            # completion_price is per token, multiply by max_tokens for this model
            model_cost = shared_tokens * completion_price
            total_cost += model_cost
        
        # Format: white text + yellow value
        if total_cost >= 0.01:
            cost_str = f"${total_cost:.4f}"
        elif total_cost >= 0.0001:
            cost_str = f"${total_cost:.6f}"
        else:
            cost_str = f"${total_cost:.10f}"

        if dynamic_pricing:
            if total_cost > 0:
                cost_summary = f"{cost_str} + dynamické"
            else:
                cost_summary = "dynamické podľa poskytovateľa"
        else:
            cost_summary = cost_str

        self.cost_label.setText(
            f'<span style="color: white;">✓ {len(selected)} modelov vybraných  |  '
            f'💰 Maximálna cena za ťah: </span>'
            f'<span style="color: #ffd54f; font-weight: bold;">{cost_summary}</span>'
        )
        self.cost_label.setStyleSheet(
            "padding: 10px; background: #173422; border-radius: 6px; "
            "font-size: 13px; font-weight: bold; border: 2px solid #4caf50;"
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
        
        # Save team (always save - create default name if needed)
        from datetime import datetime
        
        # If no team name or "[ Nový team ]", create default name
        if not self.current_team_name or self.current_team_name == "[ Nový team ]":
            self.current_team_name = "OpenRouter Team"
            log.info("Auto-creating OpenRouter team with default name: %s", self.current_team_name)
        
        selected_ids = [m["id"] for m in self.selected_models if m.get("id")]
        try:
            timeout_seconds = int(os.getenv("AI_MOVE_TIMEOUT_SECONDS", "120"))
        except ValueError:
            timeout_seconds = 120
        team = TeamConfig(
            name=self.current_team_name,
            provider="openrouter",
            model_ids=selected_ids,  # Just IDs, not full objects
            timeout_seconds=max(5, timeout_seconds),
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat(),
        )
        self.team_manager.save_team(team)
        self.team_manager.save_active_team("openrouter", self.current_team_name)
        log.info("Saved OpenRouter team '%s' with %d model IDs", self.current_team_name, len(selected_ids))
        
        self.accept()
    
    def _small_button_style(self) -> str:
        return (
            "QPushButton { "
            "background: #2f8f46; color: #0b1c00; font-weight: bold; "
            "padding: 6px 12px; border-radius: 6px; font-size: 11px; border: 1px solid #246c34; "
            "} "
            "QPushButton:hover { background: #3fa75a; } "
            "QPushButton:pressed { background: #236a34; color: #d7f4dd; }"
        )
    
    def _small_button_style_danger(self) -> str:
        return (
            "QPushButton { "
            "background: #c62828; color: white; font-weight: bold; "
            "padding: 6px 12px; border-radius: 6px; font-size: 11px; border: 1px solid #8e0000; "
            "} "
            "QPushButton:hover { background: #d32f2f; } "
            "QPushButton:pressed { background: #b71c1c; }"
        )
    
    def _populate_team_combo(self) -> None:
        """Populate team selector with available teams."""
        if self.team_combo is None:
            return
        
        # Block signals during population to avoid triggering _on_team_changed
        self.team_combo.blockSignals(True)
        try:
            self.team_combo.clear()
            
            # Load existing teams
            teams = self.team_manager.list_teams("openrouter")
            
            # Add existing teams only (no "New Team" placeholder)
            for team in teams:
                self.team_combo.addItem(team.name, team.name)
            
            # Select current team if specified
            if self.current_team_name:
                for i in range(self.team_combo.count()):
                    if self.team_combo.itemData(i) == self.current_team_name:
                        self.team_combo.setCurrentIndex(i)
                        break
        finally:
            self.team_combo.blockSignals(False)
    
    def _load_team_selections(self, team_name: str) -> None:
        """Load team's model selections and check the appropriate checkboxes.
        
        Args:
            team_name: Name of team to load
        """
        if not team_name:
            return
        
        # Load this specific team's configuration if it exists
        team_path = self.team_manager.get_team_path("openrouter", team_name)
        if not team_path.exists():
            # Team doesn't exist yet (newly created) - keep current selections
            log.info("Team '%s' is new, keeping current selections", team_name)
            return
        
        try:
            import json
            with team_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            team = TeamConfig.from_dict(data)
            
            # Clear current selections and load team's saved selections
            self._clear_selection()
            for model_id in team.model_ids:
                if model_id in self.model_checkboxes:
                    self.model_checkboxes[model_id].setChecked(True)
                    self._selection_state[model_id] = True
                else:
                    log.warning("Model '%s' from team not found in available models", model_id)
            
            self._update_cost()
            log.info("Loaded team '%s' with %d models", team_name, len(team.model_ids))
        except Exception as e:
            log.warning("Failed to load team '%s': %s", team_name, e)
            # Don't clear on error - keep current selections
    
    def _on_team_changed(self, index: int) -> None:
        """Handle team selection change."""
        if self.team_combo is None:
            return
        
        team_name = self.team_combo.itemData(index)
        
        # Update current team name
        self.current_team_name = team_name
        
        # Load team selections (only works if models are already loaded)
        if team_name:
            self._load_team_selections(team_name)
    
    def _create_new_team(self) -> None:
        """Create a new team with empty selection."""
        team_name, ok = QInputDialog.getText(
            self,
            "Nový Team",
            "Zadajte názov nového teamu:",
            text="OpenRouter Team"
        )
        
        if ok and team_name:
            # Clear all selections for fresh start
            self._clear_selection()
            
            # Add to combo
            if self.team_combo:
                # Block signals to prevent _on_team_changed from triggering
                self.team_combo.blockSignals(True)
                self.team_combo.addItem(team_name, team_name)
                # Select the new team
                self.team_combo.setCurrentIndex(self.team_combo.count() - 1)
                self.team_combo.blockSignals(False)
                
                # Update current team name
                self.current_team_name = team_name
                log.info("Created new team '%s' with empty selection", team_name)
    
    def _rename_team(self) -> None:
        """Rename current team."""
        if not self.team_combo or not self.current_team_name:
            QMessageBox.warning(self, "Premenovať", "Vyberte team na premenovanie.")
            return
        
        new_name, ok = QInputDialog.getText(
            self,
            "Premenovať Team",
            "Zadajte nový názov:",
            text=self.current_team_name
        )
        
        if ok and new_name and new_name != self.current_team_name:
            # Update combo
            current_index = self.team_combo.currentIndex()
            self.team_combo.setItemText(current_index, new_name)
            self.team_combo.setItemData(current_index, new_name)
            self.current_team_name = new_name
    
    def _delete_team(self) -> None:
        """Delete current team with confirmation."""
        if not self.team_combo or not self.current_team_name:
            QMessageBox.warning(self, "Zmazať", "Vyberte team na zmazanie.")
            return
        
        # Confirmation dialog
        reply = QMessageBox.question(
            self,
            "Potvrdiť zmazanie",
            f"Naozaj chcete zmazať team '{self.current_team_name}'?\n\n"
            "Táto akcia je nevratná.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            try:
                deleted_name = self.current_team_name
                
                # Delete team file
                team_path = self.team_manager.get_team_path("openrouter", self.current_team_name)
                if team_path.exists():
                    team_path.unlink()
                    log.info("Deleted OpenRouter team: %s", self.current_team_name)
                
                # Remove from combo
                current_index = self.team_combo.currentIndex()
                self.team_combo.removeItem(current_index)
                
                # Clear selections and reset current team
                self.current_team_name = None
                self._clear_selection()
                
                # Select first team if any exist, otherwise leave empty
                if self.team_combo.count() > 0:
                    self.team_combo.setCurrentIndex(0)
                
                QMessageBox.information(
                    self,
                    "Team zmazaný",
                    f"Team '{deleted_name}' bol úspešne zmazaný."
                )
            except Exception as e:
                log.error("Failed to delete team: %s", e)
                QMessageBox.critical(
                    self,
                    "Chyba",
                    f"Nepodarilo sa zmazať team:\n{e}"
                )
    
    def _clear_selection(self) -> None:
        """Clear all model selections."""
        for checkbox in self.model_checkboxes.values():
            checkbox.setChecked(False)
        self._selection_state.clear()
        self._update_cost()
    
    def get_selected_models(self) -> list[dict[str, Any]]:
        """Get selected models with their configurations."""
        return self.selected_models

    def get_shared_tokens_value(self) -> int:
        """Return the shared max token setting for selected models."""
        return self._default_shared_tokens
