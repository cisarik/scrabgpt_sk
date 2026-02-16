"""Dialog pre výber modelu s agentom v slovenčine."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Optional

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QComboBox, QMessageBox, QWidget, QProgressBar,
)
from PySide6.QtGui import QTextCursor

from ..ai.model_selector_agent import ModelSelectorAgent, SelectionCriteria
from ..ai.model_fetcher import fetch_openai_models, enrich_models_with_pricing

log = logging.getLogger("scrabgpt.ui.model_selector")


class ModelSelectorDialog(QDialog):
    """Dialog pre výber OpenAI modelu pomocou agenta.
    
    Zobrazuje:
    - Priebeh práce agenta v slovenčine
    - Thinking process
    - Nájdené modely s cenami
    - Dropdown na výber modelu
    """
    
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """Initialize dialog.
        
        Args:
            parent: Parent widget
        """
        super().__init__(parent)
        
        self.selected_model: Optional[str] = None
        self.models_data: list[dict[str, Any]] = []
        
        self.setWindowTitle("Nastavenie AI Modelu")
        self.setModal(True)
        self.resize(800, 600)
        
        self._setup_ui()
        self._start_agent()
    
    def _setup_ui(self) -> None:
        """Setup UI components v slovenčine."""
        # Štýl podobný Settings (menej zelenej, viac neutrálnej)
        self.setStyleSheet(
            "QDialog { background-color: #1a1a1a; color: #e8e8e8; }"
            "QLabel { color: #e8e8e8; }"
            "QTextEdit { "
            "background-color: #2a2a2a; color: #e8e8e8; "
            "border: 1px solid #404040; border-radius: 4px; "
            "font-family: 'Consolas', 'Monaco', monospace; font-size: 11px; "
            "}"
            "QComboBox { "
            "background-color: #2a2a2a; color: #e8e8e8; "
            "border: 1px solid #404040; border-radius: 4px; "
            "padding: 6px 10px; font-size: 12px; "
            "}"
            "QComboBox::drop-down { border: none; }"
            "QComboBox::down-arrow { "
            "image: none; width: 12px; height: 12px; "
            "border-left: 5px solid transparent; "
            "border-right: 5px solid transparent; "
            "border-top: 5px solid #e8e8e8; "
            "}"
            "QComboBox:hover { border-color: #5a9fd4; }"
            "QComboBox QAbstractItemView { "
            "background-color: #2a2a2a; color: #e8e8e8; "
            "selection-background-color: #3a5a7a; "
            "border: 1px solid #404040; "
            "}"
            "QProgressBar { "
            "background-color: #2a2a2a; border: 1px solid #404040; "
            "border-radius: 4px; text-align: center; height: 20px; "
            "}"
            "QProgressBar::chunk { "
            "background-color: #5a9fd4; border-radius: 3px; "
            "}"
        )
        
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Nadpis
        title = QLabel("🤖 Inteligentný Výber Modelu")
        title.setStyleSheet(
            "font-size: 18px; font-weight: bold; color: #e8e8e8; "
            "padding: 8px 0px;"
        )
        layout.addWidget(title)
        
        # Popis
        desc = QLabel(
            "Agent analyzuje dostupné OpenAI modely a ich ceny, "
            "aby vám pomohol vybrať optimálny model."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #a8a8a8; font-size: 11px; padding-bottom: 8px;")
        layout.addWidget(desc)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)  # Indeterminate
        self.progress_bar.setTextVisible(False)
        layout.addWidget(self.progress_bar)
        
        # Status label
        self.status_label = QLabel("⏳ Inicializujem agenta...")
        self.status_label.setStyleSheet(
            "color: #5a9fd4; font-weight: bold; font-size: 12px; "
            "padding: 4px 8px; background: #2a3a4a; border-radius: 4px;"
        )
        layout.addWidget(self.status_label)
        
        # Log/thinking area
        log_label = QLabel("📋 Priebeh práce agenta:")
        log_label.setStyleSheet("font-weight: bold; font-size: 12px; margin-top: 8px;")
        layout.addWidget(log_label)
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(200)
        layout.addWidget(self.log_text)
        
        # Results section (initially hidden)
        self.results_widget = QWidget()
        results_layout = QVBoxLayout(self.results_widget)
        results_layout.setContentsMargins(0, 8, 0, 0)
        results_layout.setSpacing(8)
        
        results_title = QLabel("✅ Nájdené Modely:")
        results_title.setStyleSheet("font-weight: bold; font-size: 12px;")
        results_layout.addWidget(results_title)
        
        # Model selection
        selection_layout = QHBoxLayout()
        
        model_label = QLabel("Vyberte model:")
        model_label.setStyleSheet("font-size: 12px;")
        selection_layout.addWidget(model_label)
        
        self.model_combo = QComboBox()
        self.model_combo.setSizePolicy(
            self.model_combo.sizePolicy().horizontalPolicy(),
            self.model_combo.sizePolicy().verticalPolicy()
        )
        self.model_combo.currentTextChanged.connect(self._on_model_changed)
        selection_layout.addWidget(self.model_combo, 1)
        
        results_layout.addLayout(selection_layout)
        
        # Model details
        self.details_label = QLabel()
        self.details_label.setWordWrap(True)
        self.details_label.setStyleSheet(
            "background: #2a2a2a; padding: 10px; border-radius: 4px; "
            "border: 1px solid #404040; font-size: 11px; color: #c8c8c8;"
        )
        results_layout.addWidget(self.details_label)
        
        self.results_widget.setVisible(False)
        layout.addWidget(self.results_widget)
        
        layout.addStretch()
        
        # Buttons
        button_layout = QHBoxLayout()
        button_layout.setSpacing(8)
        button_layout.addStretch()
        
        self.cancel_btn = QPushButton("✗ Zrušiť")
        self.cancel_btn.clicked.connect(self.reject)
        self.cancel_btn.setStyleSheet(
            "QPushButton { "
            "padding: 10px 20px; font-size: 13px; border-radius: 6px; "
            "background-color: #2a2a2a; color: #c8c8c8; border: 1px solid #404040; "
            "} "
            "QPushButton:hover { background-color: #3a3a3a; border-color: #5a5a5a; } "
            "QPushButton:pressed { background-color: #1a1a1a; }"
        )
        button_layout.addWidget(self.cancel_btn)
        
        self.ok_btn = QPushButton("✓ Použiť Vybraný Model")
        self.ok_btn.setEnabled(False)
        self.ok_btn.clicked.connect(self.accept)
        self.ok_btn.setStyleSheet(
            "QPushButton { "
            "padding: 10px 20px; font-size: 13px; font-weight: bold; border-radius: 6px; "
            "background-color: #3a5a7a; color: #e8e8e8; border: 2px solid #5a9fd4; "
            "} "
            "QPushButton:hover { background-color: #4a6a8a; } "
            "QPushButton:pressed { background-color: #2a4a6a; } "
            "QPushButton:disabled { "
            "background-color: #2a2a2a; color: #5a5a5a; border-color: #3a3a3a; "
            "}"
        )
        button_layout.addWidget(self.ok_btn)
        
        layout.addLayout(button_layout)
    
    def _start_agent(self) -> None:
        """Spustí agenta v samostatnom vlákne."""
        self.agent_thread = AgentWorkerThread()
        self.agent_thread.status_updated.connect(self._on_status_update)
        self.agent_thread.log_message.connect(self._on_log_message)
        self.agent_thread.thinking.connect(self._on_thinking)
        self.agent_thread.models_found.connect(self._on_models_found)
        self.agent_thread.finished_signal.connect(self._on_agent_finished)
        self.agent_thread.error_occurred.connect(self._on_agent_error)
        
        self.agent_thread.start()
    
    def _on_status_update(self, status: str) -> None:
        """Update status label."""
        self.status_label.setText(status)
    
    def _on_log_message(self, message: str) -> None:
        """Append log message."""
        self.log_text.append(message)
        self.log_text.moveCursor(QTextCursor.MoveOperation.End)
    
    def _on_thinking(self, thought: str) -> None:
        """Show agent's thinking."""
        self.log_text.append(f"<span style='color: #8a9aaa;'>💭 {thought}</span>")
        self.log_text.moveCursor(QTextCursor.MoveOperation.End)
    
    def _on_models_found(self, models: list[dict[str, Any]]) -> None:
        """Handle found models."""
        self.models_data = models
        
        # Save to openai.models file
        self._save_models_to_file(models)
        
        # Populate combo box
        self.model_combo.clear()
        for model in models:
            display_text = self._format_model_display(model)
            self.model_combo.addItem(display_text, model)
        
        # Show results
        self.results_widget.setVisible(True)
        self.ok_btn.setEnabled(True)
        
        # Select best model by default (first one)
        if models:
            self.model_combo.setCurrentIndex(0)
    
    def _on_agent_finished(self) -> None:
        """Agent finished successfully."""
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(1)
        self.status_label.setText("✅ Hotovo! Vyberte model z dropdown menu.")
        self.status_label.setStyleSheet(
            "color: #6ac46a; font-weight: bold; font-size: 12px; "
            "padding: 4px 8px; background: #2a3a2a; border-radius: 4px;"
        )
    
    def _on_agent_error(self, error: str) -> None:
        """Handle agent error."""
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        self.status_label.setText(f"❌ Chyba: {error}")
        self.status_label.setStyleSheet(
            "color: #d46a6a; font-weight: bold; font-size: 12px; "
            "padding: 4px 8px; background: #3a2a2a; border-radius: 4px;"
        )
        
        QMessageBox.warning(
            self,
            "Chyba",
            f"Agent narazil na chybu:\n\n{error}"
        )
    
    def _format_model_display(self, model: dict[str, Any]) -> str:
        """Format model for display in combo box."""
        name = model.get("id", "unknown")
        
        # Get pricing if available
        pricing = model.get("pricing")
        if pricing:
            input_price = pricing.get("input", 0)
            output_price = pricing.get("output", 0)
            price_str = f" — ${input_price:.2f}/${output_price:.2f} / 1M tokenov"
        else:
            price_str = ""
        
        # Get tier
        tier = model.get("tier", "unknown")
        tier_emoji = {
            "flagship": "👑",
            "reasoning": "🧠",
            "premium": "⭐",
            "efficient": "💨",
            "legacy": "📦",
        }.get(tier, "❓")
        
        return f"{tier_emoji} {name}{price_str}"
    
    def _on_model_changed(self, text: str) -> None:
        """Update details when model selection changes."""
        index = self.model_combo.currentIndex()
        if index < 0:
            return
        
        model = self.model_combo.itemData(index)
        if not model:
            return
        
        # Format details
        details = []
        details.append(f"<b>Model:</b> {model.get('id', 'unknown')}")
        details.append(f"<b>Typ:</b> {model.get('tier', 'unknown')}")
        
        if "context_window" in model:
            ctx = model["context_window"]
            details.append(f"<b>Context window:</b> {ctx:,} tokenov")
        
        if "max_output_tokens" in model:
            out = model["max_output_tokens"]
            details.append(f"<b>Max output:</b> {out:,} tokenov")
        
        pricing = model.get("pricing")
        if pricing:
            input_price = pricing.get("input", 0)
            output_price = pricing.get("output", 0)
            details.append(
                f"<b>Ceny:</b> ${input_price:.4f} / ${output_price:.4f} za 1M tokenov "
                f"(vstup/výstup)"
            )
        
        if "score" in model:
            score = model["score"]
            details.append(f"<b>Skóre agenta:</b> {score:.1f}/100")
        
        if "reasoning" in model:
            reasoning = model["reasoning"]
            details.append(f"<br><b>Odôvodnenie:</b><br>{reasoning}")
        
        self.details_label.setText("<br>".join(details))
        
        # Store selected model
        self.selected_model = model.get("id")
    
    def _save_models_to_file(self, models: list[dict[str, Any]]) -> None:
        """Save models to openai.models file."""
        try:
            # Get project root
            root_dir = Path(__file__).resolve().parents[2]
            output_file = root_dir / "openai.models"
            
            # Prepare data
            data = {
                "models": models,
                "count": len(models),
                "timestamp": __import__("datetime").datetime.now().isoformat(),
            }
            
            # Save
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            log.info(f"Models saved to {output_file}")
            self._on_log_message(
                f"<span style='color: #6ac46a;'>✓ Modely uložené do {output_file.name}</span>"
            )
        
        except Exception as e:
            log.exception("Error saving models to file")
            self._on_log_message(
                f"<span style='color: #d46a6a;'>⚠ Chyba pri ukladaní: {e}</span>"
            )
    
    def get_selected_model(self) -> Optional[str]:
        """Get selected model ID.
        
        Returns:
            Selected model ID or None
        """
        return self.selected_model


class AgentWorkerThread(QThread):
    """Worker thread for agent execution."""
    
    status_updated = Signal(str)
    log_message = Signal(str)
    thinking = Signal(str)
    models_found = Signal(list)
    finished_signal = Signal()
    error_occurred = Signal(str)
    
    def run(self) -> None:
        """Run agent in background."""
        try:
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                self.error_occurred.emit("OPENAI_API_KEY nie je nastavený v .env súbore")
                return
            
            # Step 1: Fetch models
            self.status_updated.emit("📥 Sťahujem zoznam modelov z OpenAI...")
            self.log_message.emit("→ Kontaktujem OpenAI API...")
            self.thinking.emit("Potrebujem získať zoznam všetkých dostupných modelov")
            
            models = fetch_openai_models(api_key)
            if not models:
                self.error_occurred.emit("Nepodarilo sa získať modely z OpenAI")
                return
            
            self.log_message.emit(
                f"<span style='color: #6ac46a;'>✓ Načítaných {len(models)} modelov</span>"
            )
            
            # Step 2: Enrich with pricing
            self.status_updated.emit("💰 Pridávam informácie o cenách...")
            self.log_message.emit("→ Načítavam cenník z databázy...")
            self.thinking.emit("Musím spojiť modely s ich cenami, aby som mohol porovnať")
            
            enriched = enrich_models_with_pricing(models)
            self.log_message.emit(
                f"<span style='color: #6ac46a;'>✓ Pridané ceny pre "
                f"{sum(1 for m in enriched if m.get('pricing'))} modelov</span>"
            )
            
            # Step 3: Create agent and select
            self.status_updated.emit("🤖 Agent analyzuje modely...")
            self.log_message.emit("→ Vyhodnocujem modely podľa výkonu a ceny...")
            self.thinking.emit(
                "Budem hodnotiť každý model podľa: "
                "1) výkonu (tier, context, output), "
                "2) ceny (vstup + výstup), "
                "3) dostupnosti"
            )
            
            agent = ModelSelectorAgent(
                api_key=api_key,
                criteria=SelectionCriteria.BALANCED,
                exclude_preview=True,
                exclude_legacy=True,
            )
            
            # Get scored models
            self.status_updated.emit("📊 Počítam skóre pre jednotlivé modely...")
            self.log_message.emit("→ Aplikujem váhovaný scoring algoritmus...")
            
            # Filter and score (simplified - just get top models)
            text_models = agent._filter_models(enriched)
            self.thinking.emit(
                f"Po filtrovaní zostalo {len(text_models)} vhodných modelov"
            )
            
            if not text_models:
                self.error_occurred.emit("Nenašli sa žiadne vhodné modely")
                return
            
            # Score models
            scored_models = agent._score_models(text_models)
            
            # Sort by score
            scored_models.sort(key=lambda x: x.total_score, reverse=True)
            
            # Convert to dict format for display
            models_for_display = []
            for sm in scored_models[:15]:  # Top 15
                model_dict = {
                    "id": sm.model_id,
                    "tier": sm.tier,
                    "context_window": sm.context_window,
                    "max_output_tokens": sm.max_output_tokens,
                    "pricing": {
                        "input": sm.input_price,
                        "output": sm.output_price,
                    } if sm.input_price else None,
                    "score": sm.total_score,
                    "reasoning": sm.reasoning,
                }
                models_for_display.append(model_dict)
            
            self.log_message.emit(
                f"<span style='color: #6ac46a;'>"
                f"✓ Zoradených top {len(models_for_display)} modelov</span>"
            )
            
            # Emit results
            self.models_found.emit(models_for_display)
            
            # Show explanation
            self.log_message.emit("<br><b>🎯 Najlepší model:</b>")
            best = models_for_display[0]
            self.log_message.emit(
                f"<span style='color: #5a9fd4; font-weight: bold;'>"
                f"{best['id']}</span> (skóre: {best['score']:.1f}/100)"
            )
            self.log_message.emit(f"<i>{best['reasoning']}</i>")
            
            self.finished_signal.emit()
        
        except Exception as e:
            log.exception("Agent thread error")
            self.error_occurred.emit(str(e))
