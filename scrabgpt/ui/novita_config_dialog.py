"""Novita Configuration Dialog for selecting reasoning models."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from PySide6.QtCore import Qt, QThread, QObject, Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QCheckBox, QScrollArea, QWidget, QMessageBox,
    QFrame, QLineEdit, QComboBox, QProgressBar, QInputDialog,
)

from ..ai.novita import NovitaClient
from ..core.team_config import TeamConfig, get_team_manager

log = logging.getLogger("scrabgpt.ui")


class ModelFetchWorker(QObject):
    """Worker to fetch models from Novita in background."""
    
    finished = Signal(list)
    failed = Signal(str)
    
    def __init__(self, api_key: str) -> None:
        super().__init__()
        self.api_key = api_key
    
    def run(self) -> None:
        try:
            async def fetch() -> list[dict[str, Any]]:
                client = NovitaClient(self.api_key)
                models = await client.fetch_models()
                await client.close()
                return models
            
            models = asyncio.run(fetch())
            self.finished.emit(models)
        except Exception as e:
            log.exception("Failed to fetch Novita models: %s", e)
            self.failed.emit(str(e))


class NovitaConfigDialog(QDialog):
    """Dialog for configuring Novita AI models and managing teams."""
    
    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        default_tokens: int = 4096,
        current_team_name: str | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Nastaviť Novita AI Modely")
        self.setModal(True)
        self.resize(950, 700)
        
        self.models: list[dict[str, Any]] = []
        self.sorted_models: list[dict[str, Any]] = []
        self.filtered_models: list[dict[str, Any]] = []
        self.model_checkboxes: dict[str, QCheckBox] = {}
        self.selected_models: list[dict[str, Any]] = []
        self.max_selection = 10
        self._default_shared_tokens = self._clamp_shared_tokens(default_tokens)
        self.search_edit: QLineEdit | None = None
        self._search_text: str = ""
        self._selection_state: dict[str, bool] = {}
        self.team_manager = get_team_manager()
        # Load active team if not specified
        self.current_team_name = current_team_name or self.team_manager.load_active_team("novita")
        self.team_combo: QComboBox | None = None
        self.sort_combo: QComboBox | None = None
        self.progress: QProgressBar | None = None
        
        self.sort_options: list[tuple[str, str]] = [
            ("Name A-Z", "name_asc"),
            ("Context: High to Low", "context_high"),
            ("Category", "category"),
        ]

        self._setup_ui()
        self._load_models()
    
    def _setup_ui(self) -> None:
        self.setStyleSheet(
            "QDialog { background-color: #0f1a12; color: #e8f5e9; }"
            "QLabel { color: #e8f5e9; }"
            "QScrollArea { background-color: #0f1a12; }"
        )

        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(12, 12, 12, 12)

        # Top controls: Team selector + Sort + Search
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
        
        # Sort dropdown
        sort_caption = QLabel("Zoradenie:")
        sort_caption.setStyleSheet("font-size: 13px; font-weight: bold; color: #9ad0a2; margin-left: 16px;")
        controls_layout.addWidget(sort_caption)
        
        self.sort_combo = QComboBox()
        for text, key in self.sort_options:
            self.sort_combo.addItem(text, key)
        self.sort_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        self.sort_combo.setStyleSheet(
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
        self.sort_combo.currentIndexChanged.connect(self._on_sort_changed)
        controls_layout.addWidget(self.sort_combo)
        
        controls_layout.addStretch()

        # Search bar
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

        # Info label
        info = QLabel(
            "Vyber reasoning modely pre konkurenčné hranie (max. 10). "
            "Najlepší ťah (najvyššie skóre) sa použije."
        )
        info.setWordWrap(True)
        info.setStyleSheet(
            "padding: 10px 12px; background: #1b3822; border-radius: 6px; "
            "color: #e6f7eb; font-size: 13px; font-weight: bold; border: 1px solid #2f5c39;"
        )
        layout.addWidget(info)

        # Progress bar
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setTextVisible(False)
        self.progress.setStyleSheet(
            "QProgressBar { background: #132418; border: 1px solid #2f5c39; border-radius: 6px; }"
            "QProgressBar::chunk { background-color: #4caf50; border-radius: 6px; }"
        )
        layout.addWidget(self.progress)

        # Scroll area for models
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
        layout.addWidget(scroll, 1)

        # Selection info
        self.selection_label = QLabel(f"Vybrané: 0 / {self.max_selection}")
        self.selection_label.setStyleSheet(
            "font-size: 13px; font-weight: bold; color: #ffd54f; "
            "padding: 6px 12px; background: #3d2a0f; border: 1px solid #8a6a4a; border-radius: 4px;"
        )
        layout.addWidget(self.selection_label)

        # Bottom buttons
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(8)

        cancel_btn = QPushButton("✗ Zrušiť")
        cancel_btn.setStyleSheet(
            "QPushButton { padding: 8px 16px; font-size: 12px; border-radius: 6px; "
            "background-color: #182c1d; color: #b6e0bd; border: 1px solid #2f5c39; }"
            "QPushButton:hover { background-color: #213c28; }"
            "QPushButton:pressed { background-color: #112015; }"
        )
        cancel_btn.clicked.connect(self.reject)
        buttons_layout.addWidget(cancel_btn)

        buttons_layout.addStretch()

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
        buttons_layout.addWidget(self.ok_btn)

        layout.addLayout(buttons_layout)
        
        # Now connect team combo signal and populate (after all widgets exist)
        if self.team_combo:
            self._populate_team_combo()
            self.team_combo.currentIndexChanged.connect(self._on_team_changed)
    
    def _small_button_style(self) -> str:
        return (
            "QPushButton { "
            "background: #2f8f46; color: #0b1c00; font-weight: bold; "
            "padding: 6px 12px; border-radius: 6px; font-size: 11px; border: 1px solid #246c34; "
            "} "
            "QPushButton:hover { background: #3fa75a; } "
            "QPushButton:pressed { background: #236a34; color: #d7f4dd; }"
        )
    
    def _clamp_shared_tokens(self, val: int) -> int:
        return max(1000, min(val, 16000))
    
    def _load_models(self) -> None:
        """Load models from Novita."""
        import os
        api_key = os.getenv("NOVITA_API_KEY", "")
        if not api_key:
            QMessageBox.warning(
                self,
                "Chýba API kľúč",
                "NOVITA_API_KEY nie je nastavený v .env súbore.",
            )
            return

        # Show progress bar
        if self.progress:
            self.progress.setVisible(True)
        
        self.worker_obj = ModelFetchWorker(api_key)
        self.thread_obj = QThread()
        self.worker_obj.moveToThread(self.thread_obj)
        
        self.worker_obj.finished.connect(self._on_models_loaded)
        self.worker_obj.failed.connect(self._on_models_failed)
        self.thread_obj.started.connect(self.worker_obj.run)
        
        self.thread_obj.start()
    
    def _on_models_loaded(self, models: list[dict[str, Any]]) -> None:
        """Handle models loaded successfully."""
        self.thread_obj.quit()
        self.thread_obj.wait()
        
        # Hide progress bar
        if self.progress:
            self.progress.setVisible(False)
        
        self.models = models
        self.sorted_models = models
        self.filtered_models = models
        self._populate_models()
        log.info("Loaded %d Novita models", len(models))
        
        # Load active team's selections after models are loaded
        if self.current_team_name:
            self._load_team_selections(self.current_team_name)
    
    def _on_models_failed(self, error: str) -> None:
        """Handle models loading failure."""
        self.thread_obj.quit()
        self.thread_obj.wait()
        
        # Hide progress bar
        if self.progress:
            self.progress.setVisible(False)
        
        QMessageBox.critical(
            self,
            "Chyba načítania modelov",
            f"Nepodarilo sa načítať Novita modely:\n{error}",
        )
        log.error("Failed to load Novita models: %s", error)
    
    def _populate_models(self) -> None:
        """Populate models list."""
        # Clear existing
        for i in reversed(range(self.models_layout.count())):
            widget = self.models_layout.itemAt(i).widget()
            if widget:
                widget.deleteLater()

        self.model_checkboxes.clear()

        # Use filtered_models if available (already filtered by _refresh_model_list)
        visible_models = self.filtered_models if self.filtered_models else self.models

        # Group by category
        categories: dict[str, list[dict[str, Any]]] = {}
        for model in visible_models:
            cat = model.get("category", "other")
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(model)

        # Display models by category
        for category_name in sorted(categories.keys()):
            category_models = categories[category_name]

            # Category header
            cat_label = QLabel(f"▼ {category_name.upper()}")
            cat_label.setStyleSheet(
                "font-size: 13px; font-weight: bold; color: #4caf50; padding: 8px 0 4px 0;"
            )
            self.models_layout.addWidget(cat_label)

            # Models in category
            for model in category_models:
                model_widget = self._create_model_widget(model)
                self.models_layout.addWidget(model_widget)

        self.models_layout.addStretch()
        
        # Restore selection state
        for model_id, checked in self._selection_state.items():
            if model_id in self.model_checkboxes:
                self.model_checkboxes[model_id].setChecked(checked)
        
        self._update_selection_label()
    
    def _create_model_widget(self, model: dict[str, Any]) -> QWidget:
        """Create a widget for a single model."""
        container = QFrame()
        container.setFrameShape(QFrame.Shape.StyledPanel)
        container.setStyleSheet(
            "QFrame { "
            "background: #132418; border: 1px solid #2f5c39; border-radius: 4px; "
            "padding: 8px; "
            "} "
            "QFrame:hover { background: #1a3020; border-color: #4caf50; }"
        )

        layout = QHBoxLayout(container)
        layout.setSpacing(12)
        layout.setContentsMargins(8, 8, 8, 8)

        # Checkbox
        checkbox = QCheckBox()
        checkbox.setCursor(Qt.CursorShape.PointingHandCursor)
        checkbox.setStyleSheet(
            "QCheckBox::indicator { width: 20px; height: 20px; } "
            "QCheckBox::indicator:unchecked { "
            "border: 2px solid #4caf50; border-radius: 4px; background: #0a0a0a; "
            "} "
            "QCheckBox::indicator:checked { "
            "border: 2px solid #4caf50; border-radius: 4px; background: #4caf50; "
            "image: none; "
            "}"
        )
        checkbox.stateChanged.connect(lambda: self._on_model_toggled(model))
        self.model_checkboxes[model["id"]] = checkbox
        layout.addWidget(checkbox)

        # Model info
        info_layout = QVBoxLayout()
        info_layout.setSpacing(4)

        name_label = QLabel(model["name"])
        name_label.setStyleSheet("font-size: 13px; font-weight: bold; color: #e8f5e9;")
        info_layout.addWidget(name_label)

        id_label = QLabel(model["id"])
        id_label.setStyleSheet("font-size: 11px; color: #81c784;")
        info_layout.addWidget(id_label)

        context_label = QLabel(f"Context: {model.get('context_length', '?'):,} tokens")
        context_label.setStyleSheet("font-size: 11px; color: #b6e0bd;")
        info_layout.addWidget(context_label)

        layout.addLayout(info_layout, 1)

        return container
    
    def _on_model_toggled(self, model: dict[str, Any]) -> None:
        """Handle model checkbox toggle."""
        checkbox = self.model_checkboxes[model["id"]]
        self._selection_state[model["id"]] = checkbox.isChecked()

        # Check selection limit
        selected_count = sum(1 for cb in self.model_checkboxes.values() if cb.isChecked())
        
        if selected_count > self.max_selection:
            checkbox.setChecked(False)
            self._selection_state[model["id"]] = False
            QMessageBox.warning(
                self,
                "Limit výberu",
                f"Môžete vybrať maximálne {self.max_selection} modelov.",
            )
        
        self._update_selection_label()
    
    def _update_selection_label(self) -> None:
        """Update selection count label."""
        selected_count = sum(1 for state in self._selection_state.values() if state)
        self.selection_label.setText(f"Vybrané: {selected_count} / {self.max_selection}")
        
        # Enable/disable OK button
        if self.ok_btn:
            self.ok_btn.setEnabled(selected_count > 0)
    
    def _on_search_changed(self, text: str) -> None:
        """Handle search text change."""
        cleaned = text.strip()
        if cleaned == self._search_text:
            return
        self._search_text = cleaned
        self._refresh_model_list()
    
    def _select_all(self) -> None:
        """Select all visible models (up to limit)."""
        selected_count = 0
        for model_id, checkbox in self.model_checkboxes.items():
            if checkbox.isVisible() and selected_count < self.max_selection:
                checkbox.setChecked(True)
                self._selection_state[model_id] = True
                selected_count += 1
        self._update_selection_label()
    
    def _clear_selection(self) -> None:
        """Clear all selections."""
        for checkbox in self.model_checkboxes.values():
            checkbox.setChecked(False)
        self._selection_state.clear()
        self._update_selection_label()
    
    def _populate_team_combo(self) -> None:
        """Populate team selector with available teams."""
        if self.team_combo is None:
            return
        
        # Block signals during population to avoid triggering _on_team_changed
        self.team_combo.blockSignals(True)
        try:
            self.team_combo.clear()
            
            # Load existing teams
            teams = self.team_manager.list_teams("novita")
            
            # Add "New Team" option first
            self.team_combo.addItem("[ Nový team ]", None)
            
            # Add existing teams
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
        team_path = self.team_manager.get_team_path("novita", team_name)
        if not team_path.exists():
            # Team doesn't exist yet (newly created) - keep current selections
            log.info("Team '%s' is new, keeping current selections", team_name)
            return
        
        try:
            import json
            with team_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            from ..core.team_config import TeamConfig
            team = TeamConfig.from_dict(data)
            
            # Clear current selections and load team's saved selections
            self._clear_selection()
            for model_id in team.model_ids:
                if model_id in self.model_checkboxes:
                    self.model_checkboxes[model_id].setChecked(True)
                    self._selection_state[model_id] = True
                else:
                    log.warning("Model '%s' from team not found in available models", model_id)
            
            self._update_selection_label()
            log.info("Loaded team '%s' with %d models", team_name, len(team.model_ids))
        except Exception as e:
            log.warning("Failed to load team '%s': %s", team_name, e)
            # Don't clear on error - keep current selections
    
    def _on_team_changed(self, index: int) -> None:
        """Handle team selection change."""
        if self.team_combo is None:
            return
        
        team_name = self.team_combo.itemData(index)
        
        if team_name is None:
            # "[ Nový team ]" selected - clear selections for fresh start
            self._clear_selection()
            self.current_team_name = None
            return
        
        # Update current team name
        self.current_team_name = team_name
        
        # Load team selections (only works if models are already loaded)
        self._load_team_selections(team_name)
    
    def _create_new_team(self) -> None:
        """Create a new team."""
        team_name, ok = QInputDialog.getText(
            self,
            "Nový Team",
            "Zadajte názov nového teamu:",
            text="Novita Team"
        )
        
        if ok and team_name:
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
                # Don't clear selections - keep what user has already selected
                log.info("Created new team '%s' with current selections", team_name)
    
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
    
    def _on_sort_changed(self, _index: int) -> None:
        """Handle sort change."""
        self._apply_sort()
    
    def _apply_sort(self) -> None:
        """Apply current sort to models."""
        if not self.sort_combo or not self.models:
            return
        
        sort_key = self.sort_combo.currentData()
        models = list(self.models)
        
        if sort_key == "name_asc":
            models.sort(key=lambda m: m.get("name", m.get("id", "")))
        elif sort_key == "context_high":
            models.sort(key=lambda m: m.get("context_length", 0), reverse=True)
        elif sort_key == "category":
            models.sort(key=lambda m: (m.get("category", ""), m.get("name", "")))
        
        self.sorted_models = models
        self._refresh_model_list()
    
    def _refresh_model_list(self) -> None:
        """Apply search filter and repopulate."""
        base_models = self.sorted_models if self.sorted_models else self.models
        
        if self._search_text:
            needle = self._search_text.lower()
            filtered = [
                m for m in base_models
                if needle in m.get("id", "").lower() or needle in m.get("name", "").lower()
            ]
        else:
            filtered = base_models
        
        self.filtered_models = filtered
        self._populate_models()
    
    def _on_ok(self) -> None:
        """Handle OK button click."""
        selected_ids = [
            model_id for model_id, checked in self._selection_state.items() if checked
        ]
        
        if not selected_ids:
            QMessageBox.warning(
                self,
                "Žiadne modely",
                "Musíte vybrať aspoň jeden model.",
            )
            return

        # Build full model objects for runtime use (with max_tokens)
        self.selected_models = [
            {
                **model,
                "max_tokens": self._default_shared_tokens,
            }
            for model in self.models
            if model["id"] in selected_ids
        ]
        
        # Save team (create default name if needed)
        from datetime import datetime
        
        # If no team name or "[ Nový team ]", create default name
        if not self.current_team_name or self.current_team_name == "[ Nový team ]":
            self.current_team_name = "Novita Team"
            log.info("Auto-creating team with default name: %s", self.current_team_name)
        
        team = TeamConfig(
            name=self.current_team_name,
            provider="novita",
            model_ids=selected_ids,  # Just IDs, not full objects
            timeout_seconds=120,
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat(),
        )
        self.team_manager.save_team(team)
        self.team_manager.save_active_team("novita", self.current_team_name)
        log.info("Saved team '%s' with %d model IDs", self.current_team_name, len(selected_ids))
        
        log.info("Selected %d Novita models", len(self.selected_models))
        self.accept()
    
    def get_selected_models(self) -> list[dict[str, Any]]:
        """Get selected models with configuration."""
        return self.selected_models
