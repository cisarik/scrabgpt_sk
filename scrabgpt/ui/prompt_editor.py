"""AI Prompt Editor Dialog - allows customization of AI prompts."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTextEdit,
    QPushButton, QComboBox, QLabel, QMessageBox, QInputDialog, QWidget,
)

log = logging.getLogger("scrabgpt.ui")


class PromptEditorDialog(QDialog):
    """Eye-candy dialog for editing AI prompts.
    
    Features:
    - Large font text editor
    - Dropdown to select from available prompts
    - Revert to default button
    - Save/Save As functionality
    - Dark theme styling
    """
    
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.prompts_dir = Path("prompts")
        self.prompts_dir.mkdir(exist_ok=True)
        
        self.current_file = os.getenv("AI_PROMPT_FILE", "prompts/default.txt")
        self.default_file = "prompts/default.txt"
        self.modified = False
        
        self.setup_ui()
        self.load_available_prompts()
        self.load_prompt(self.current_file)
    
    def setup_ui(self) -> None:
        """Initialize the UI components."""
        self.setWindowTitle("Upraviť AI Prompt")
        self.setMinimumSize(900, 700)
        
        # Dark theme styling
        self.setStyleSheet("""
            QDialog {
                background: #1a1a1a;
                color: white;
            }
            QLabel {
                color: white;
                font-size: 13px;
            }
            QTextEdit {
                background: #2a2a2a;
                color: white;
                border: 2px solid #444;
                border-radius: 6px;
                padding: 10px;
                font-family: 'Monospace', 'Courier New';
                font-size: 14px;
                line-height: 1.5;
            }
            QComboBox {
                background: #2a2a2a;
                color: white;
                border: 2px solid #444;
                border-radius: 4px;
                padding: 6px;
                font-size: 13px;
                min-width: 250px;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid #888;
                margin-right: 5px;
            }
            QPushButton {
                background: #3a3a3a;
                color: white;
                border: 2px solid #555;
                border-radius: 4px;
                padding: 8px 16px;
                font-size: 13px;
                font-weight: 500;
            }
            QPushButton:hover {
                background: #4a4a4a;
                border-color: #666;
            }
            QPushButton:pressed {
                background: #2a2a2a;
            }
            QPushButton#defaultBtn {
                background: #6a4a2a;
                border-color: #8a6a4a;
            }
            QPushButton#defaultBtn:hover {
                background: #7a5a3a;
            }
            QPushButton#saveBtn {
                background: #2a5a3a;
                border-color: #4a7a5a;
            }
            QPushButton#saveBtn:hover {
                background: #3a6a4a;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Header with prompt selector
        header_layout = QHBoxLayout()
        
        prompt_label = QLabel("Vyberte prompt:")
        header_layout.addWidget(prompt_label)
        
        self.prompt_combo = QComboBox()
        self.prompt_combo.currentTextChanged.connect(self._on_prompt_selected)
        header_layout.addWidget(self.prompt_combo)
        
        header_layout.addStretch()
        
        # Info label
        self.info_label = QLabel("Upravte prompt podľa potreby. Použite {language}, {tile_summary}, {compact_state}, {premium_legend}")
        self.info_label.setStyleSheet("color: #888; font-size: 11px; font-style: italic;")
        self.info_label.setWordWrap(True)
        header_layout.addWidget(self.info_label)
        
        layout.addLayout(header_layout)
        
        # Text editor
        self.text_edit = QTextEdit()
        font = QFont("Monospace")
        font.setPointSize(12)
        self.text_edit.setFont(font)
        self.text_edit.textChanged.connect(self._on_text_changed)
        layout.addWidget(self.text_edit)
        
        # Bottom buttons
        button_layout = QHBoxLayout()
        
        self.default_btn = QPushButton("🔄 Vrátiť na pôvodný")
        self.default_btn.setObjectName("defaultBtn")
        self.default_btn.clicked.connect(self._revert_to_default)
        button_layout.addWidget(self.default_btn)
        
        button_layout.addStretch()
        
        self.save_btn = QPushButton("💾 Uložiť")
        self.save_btn.setObjectName("saveBtn")
        self.save_btn.clicked.connect(self._save_prompt)
        button_layout.addWidget(self.save_btn)
        
        self.save_as_btn = QPushButton("💾 Uložiť ako...")
        self.save_as_btn.clicked.connect(self._save_prompt_as)
        button_layout.addWidget(self.save_as_btn)
        
        cancel_btn = QPushButton("❌ Zrušiť")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)
        
        ok_btn = QPushButton("✓ Použiť")
        ok_btn.clicked.connect(self._apply_and_close)
        button_layout.addWidget(ok_btn)
        
        layout.addLayout(button_layout)
    
    def load_available_prompts(self) -> None:
        """Load all available prompt files from prompts/ directory."""
        self.prompt_combo.clear()
        
        if not self.prompts_dir.exists():
            return
        
        prompt_files = sorted(self.prompts_dir.glob("*.txt"))
        
        for prompt_file in prompt_files:
            display_name = prompt_file.stem
            self.prompt_combo.addItem(display_name, str(prompt_file))
        
        # Select current file
        for i in range(self.prompt_combo.count()):
            if self.prompt_combo.itemData(i) == self.current_file:
                self.prompt_combo.setCurrentIndex(i)
                break
    
    def load_prompt(self, filepath: str) -> None:
        """Load prompt from file."""
        try:
            path = Path(filepath)
            if path.exists():
                content = path.read_text(encoding="utf-8")
                self.text_edit.blockSignals(True)
                self.text_edit.setPlainText(content)
                self.text_edit.blockSignals(False)
                self.current_file = filepath
                self.modified = False
                log.info("Loaded prompt from %s", filepath)
            else:
                log.warning("Prompt file not found: %s", filepath)
                QMessageBox.warning(
                    self,
                    "Súbor nenájdený",
                    f"Prompt súbor nenájdený: {filepath}"
                )
        except Exception as e:
            log.exception("Failed to load prompt: %s", e)
            QMessageBox.critical(
                self,
                "Chyba načítania",
                f"Nepodarilo sa načítať prompt: {e}"
            )
    
    def save_prompt(self, filepath: str) -> bool:
        """Save current prompt to file."""
        try:
            path = Path(filepath)
            path.parent.mkdir(parents=True, exist_ok=True)
            
            content = self.text_edit.toPlainText()
            path.write_text(content, encoding="utf-8")
            
            self.current_file = filepath
            self.modified = False
            log.info("Saved prompt to %s", filepath)
            return True
        except Exception as e:
            log.exception("Failed to save prompt: %s", e)
            QMessageBox.critical(
                self,
                "Chyba uloženia",
                f"Nepodarilo sa uložiť prompt: {e}"
            )
            return False
    
    def _on_prompt_selected(self, display_name: str) -> None:
        """Handle prompt selection from dropdown."""
        if not display_name:
            return
        
        filepath = self.prompt_combo.currentData()
        if filepath and filepath != self.current_file:
            if self.modified:
                reply = QMessageBox.question(
                    self,
                    "Neuložené zmeny",
                    "Máte neuložené zmeny. Chcete ich uložiť pred načítaním iného promptu?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel
                )
                
                if reply == QMessageBox.StandardButton.Cancel:
                    # Revert combo selection
                    for i in range(self.prompt_combo.count()):
                        if self.prompt_combo.itemData(i) == self.current_file:
                            self.prompt_combo.blockSignals(True)
                            self.prompt_combo.setCurrentIndex(i)
                            self.prompt_combo.blockSignals(False)
                            break
                    return
                elif reply == QMessageBox.StandardButton.Yes:
                    self._save_prompt()
            
            self.load_prompt(filepath)
    
    def _on_text_changed(self) -> None:
        """Mark prompt as modified when text changes."""
        self.modified = True
    
    def _revert_to_default(self) -> None:
        """Revert current prompt to default."""
        reply = QMessageBox.question(
            self,
            "Potvrdiť obnovenie",
            "Naozaj chcete obnoviť pôvodný prompt? Všetky neuložené zmeny budú stratené.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.load_prompt(self.default_file)
    
    def _save_prompt(self) -> None:
        """Save current prompt to current file."""
        if self.save_prompt(self.current_file):
            QMessageBox.information(
                self,
                "Uložené",
                f"Prompt bol úspešne uložený do {Path(self.current_file).name}"
            )
    
    def _save_prompt_as(self) -> None:
        """Save current prompt to a new file."""
        name, ok = QInputDialog.getText(
            self,
            "Uložiť ako",
            "Zadajte názov pre nový prompt (bez prípony):"
        )
        
        if ok and name:
            # Sanitize filename
            name = "".join(c for c in name if c.isalnum() or c in (' ', '-', '_')).strip()
            if not name:
                QMessageBox.warning(
                    self,
                    "Neplatný názov",
                    "Názov musí obsahovať aspoň jeden alfanumerický znak."
                )
                return
            
            filepath = str(self.prompts_dir / f"{name}.txt")
            
            if Path(filepath).exists():
                reply = QMessageBox.question(
                    self,
                    "Súbor existuje",
                    f"Súbor {name}.txt už existuje. Chcete ho prepísať?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                
                if reply != QMessageBox.StandardButton.Yes:
                    return
            
            if self.save_prompt(filepath):
                # Reload available prompts and select the new one
                self.load_available_prompts()
                QMessageBox.information(
                    self,
                    "Uložené",
                    f"Prompt bol úspešne uložený ako {name}.txt"
                )
    
    def _apply_and_close(self) -> None:
        """Apply current prompt and close dialog."""
        if self.modified:
            reply = QMessageBox.question(
                self,
                "Neuložené zmeny",
                "Máte neuložené zmeny. Chcete ich uložiť?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel
            )
            
            if reply == QMessageBox.StandardButton.Cancel:
                return
            elif reply == QMessageBox.StandardButton.Yes:
                if not self.save_prompt(self.current_file):
                    return
        
        # Update environment variable
        os.environ["AI_PROMPT_FILE"] = self.current_file
        
        self.accept()
    
    def get_current_prompt_file(self) -> str:
        """Return the currently selected prompt file path."""
        return self.current_file
