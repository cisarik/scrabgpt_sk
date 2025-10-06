"""Response Detail Dialog - shows raw model response and GPT analysis."""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QWidget, QSplitter,
)

log = logging.getLogger("scrabgpt.ui")


class ResponseDetailDialog(QDialog):
    """Dialog showing raw model response and GPT analysis."""
    
    def __init__(self, result_data: dict[str, Any], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.result_data = result_data
        self.setWindowTitle(f"Response Detail: {result_data.get('model_name', 'Unknown')}")
        self.setModal(True)
        self.resize(900, 700)
        
        self._setup_ui()
    
    def _setup_ui(self) -> None:
        """Setup the dialog UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)
        
        # Header with model info
        header = QLabel(f"<b>Model:</b> {self.result_data.get('model_name', 'Unknown')}")
        header.setStyleSheet("font-size: 14px; padding: 8px; background: #2a2a2a; border-radius: 4px; color: white;")
        layout.addWidget(header)
        
        # Status and score info
        status = self.result_data.get("status", "unknown")
        score = self.result_data.get("score", -1)
        judge_valid = self.result_data.get("judge_valid")
        prompt_tokens = self.result_data.get("prompt_tokens")
        completion_tokens = self.result_data.get("completion_tokens")

        info_text = f"<b>Status:</b> {status} | <b>Score:</b> {score}"
        if judge_valid is not None:
            info_text += f" | <b>Judge:</b> {'✓ Valid' if judge_valid else '✗ Invalid'}"
        if isinstance(prompt_tokens, int) or isinstance(completion_tokens, int):
            info_text += (
                f" | <b>Tokens:</b> P {prompt_tokens or 0} / C {completion_tokens or 0}"
            )

        info_label = QLabel(info_text)
        info_label.setStyleSheet("font-size: 12px; padding: 6px; color: #ccc;")
        layout.addWidget(info_label)

        # OpenRouter metadata (trace + timing)
        openrouter_meta = self.result_data.get("openrouter", {}) or {}
        meta_bits: list[str] = []
        call_id = openrouter_meta.get("call_id")
        if call_id:
            meta_bits.append(f"<b>Call ID:</b> {call_id}")
        trace_id = openrouter_meta.get("trace_id")
        if trace_id:
            meta_bits.append(f"<b>Trace:</b> {trace_id}")
        elapsed = openrouter_meta.get("elapsed")
        if isinstance(elapsed, (int, float)):
            meta_bits.append(f"<b>Duration:</b> {elapsed:.2f}s")
        limit = openrouter_meta.get("timeout_seconds")
        if isinstance(limit, (int, float)):
            meta_bits.append(f"<b>Limit:</b> {int(limit)}s")
        if meta_bits:
            meta_label = QLabel(" | ".join(meta_bits))
            meta_label.setStyleSheet("font-size: 11px; color: #aaaaaa; padding: 4px 6px;")
            layout.addWidget(meta_label)
        
        # Splitter for raw response and analysis
        splitter = QSplitter(Qt.Orientation.Vertical)
        
        # Raw response section
        raw_widget = QWidget()
        raw_layout = QVBoxLayout(raw_widget)
        raw_layout.setContentsMargins(0, 0, 0, 0)
        raw_layout.setSpacing(4)
        
        raw_title = QLabel("📄 Raw Response from Model")
        raw_title.setStyleSheet(
            "font-size: 13px; font-weight: bold; padding: 6px; "
            "background: #1a4d1a; color: white; border-radius: 4px;"
        )
        raw_layout.addWidget(raw_title)
        
        self.raw_text = QTextEdit()
        self.raw_text.setReadOnly(True)
        self.raw_text.setStyleSheet(
            "QTextEdit { "
            "background: #0d0d0d; color: #e0e0e0; "
            "border: 1px solid #444; border-radius: 4px; "
            "font-family: 'Fira Code', 'Courier New', monospace; font-size: 13px; "
            "padding: 8px; "
            "}"
        )
        raw_content = self.result_data.get("raw_response", "")
        if not raw_content:
            raw_content = self.result_data.get("error", "No response available")
        self.raw_text.setPlainText(raw_content)
        raw_layout.addWidget(self.raw_text)
        
        splitter.addWidget(raw_widget)
        
        # GPT analysis section
        analysis_widget = QWidget()
        analysis_layout = QVBoxLayout(analysis_widget)
        analysis_layout.setContentsMargins(0, 0, 0, 0)
        analysis_layout.setSpacing(4)
        
        analysis_title = QLabel("🤖 GPT-5-mini Analysis")
        analysis_title.setStyleSheet(
            "font-size: 13px; font-weight: bold; padding: 6px; "
            "background: #1a3a4d; color: white; border-radius: 4px;"
        )
        analysis_layout.addWidget(analysis_title)
        
        self.analysis_text = QTextEdit()
        self.analysis_text.setReadOnly(True)
        self.analysis_text.setStyleSheet(
            "QTextEdit { "
            "background: #0d0d0d; color: #e0e0e0; "
            "border: 1px solid #444; border-radius: 4px; "
            "font-family: 'Fira Code', 'Courier New', monospace; font-size: 13px; "
            "padding: 8px; "
            "}"
        )
        
        # Check for error analysis first (for parse errors)
        error_analysis = self.result_data.get("error_analysis", "")
        gpt_analysis = self.result_data.get("gpt_analysis", "")
        
        if error_analysis:
            # Show error analysis for parse errors
            self.analysis_text.setPlainText(error_analysis)
        elif gpt_analysis:
            # Show GPT analysis if available
            self.analysis_text.setPlainText(gpt_analysis)
        elif status == "ok":
            # Successful parse, show the move details
            try:
                move = self.result_data.get("move", {})
                words = self.result_data.get("words", [])
                judge_valid = self.result_data.get("judge_valid")
                judge_reason = self.result_data.get("judge_reason", "")
                
                analysis_lines = ["✓ Successfully parsed as valid JSON", ""]
                
                if words:
                    analysis_lines.append(f"📝 Words formed: {', '.join(words)}")
                    if judge_valid is not None:
                        if judge_valid:
                            analysis_lines.append("✓ Judge: All words are valid")
                        else:
                            analysis_lines.append(f"✗ Judge: Invalid ({judge_reason})")
                    analysis_lines.append("")
                
                if move and isinstance(move, dict):
                    placements = move.get("placements", [])
                    if placements:
                        analysis_lines.append(f"🎯 Placements: {len(placements)} tiles")
                        analysis_lines.append("")
                        for p in placements[:10]:  # Show first 10
                            if isinstance(p, dict):
                                analysis_lines.append(
                                    f"  ({p.get('row', '?')}, {p.get('col', '?')}): {p.get('letter', '?')}"
                                )
                        if len(placements) > 10:
                            analysis_lines.append(f"  ... and {len(placements) - 10} more")

                breakdown = self.result_data.get("score_breakdown") or []
                if breakdown:
                    analysis_lines.append("")
                    analysis_lines.append("📊 Score breakdown:")
                    for entry in breakdown:
                        try:
                            word = entry.get("word", "?")
                            total = entry.get("total", 0)
                            base = entry.get("base_points", 0)
                            bonus = entry.get("letter_bonus_points", 0)
                            multiplier = entry.get("word_multiplier", 1)
                            analysis_lines.append(
                                f"  {word}: {total} (base {base} + bonus {bonus}) x{multiplier}"
                            )
                        except Exception:
                            continue

                self.analysis_text.setPlainText("\n".join(analysis_lines))
            except Exception as e:
                self.analysis_text.setPlainText(f"Error displaying move details: {e}")
        elif status == "invalid":
            # Invalid move, show reason
            judge_reason = self.result_data.get("judge_reason", "")
            error = self.result_data.get("error", "")
            
            analysis_lines = ["✗ Move was marked as invalid", ""]
            if judge_reason:
                analysis_lines.append(f"Judge reason: {judge_reason}")
            if error:
                analysis_lines.append(f"Error: {error}")
            
            self.analysis_text.setPlainText("\n".join(analysis_lines))
        elif status == "timeout":
            limit = openrouter_meta.get("timeout_seconds")
            limit_text = f"{int(limit)}s" if isinstance(limit, (int, float)) else "konfigurovanom limite"
            error = self.result_data.get("error", "Volanie prekročilo časový limit.")
            self.analysis_text.setPlainText(
                f"⏱ Model prekročil {limit_text}.\n\n{error}"
            )
        else:
            self.analysis_text.setPlainText("No analysis available (model returned error or empty response)")
        
        analysis_layout.addWidget(self.analysis_text)
        
        splitter.addWidget(analysis_widget)
        
        # Set initial splitter sizes (50/50)
        splitter.setSizes([350, 350])
        
        layout.addWidget(splitter)
        
        # Close button
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        close_btn = QPushButton("✓ Close")
        close_btn.clicked.connect(self.accept)
        close_btn.setStyleSheet(
            "QPushButton { "
            "background: #4caf50; color: white; font-weight: bold; "
            "padding: 8px 24px; border-radius: 4px; font-size: 12px; "
            "} "
            "QPushButton:hover { background: #45a049; }"
        )
        button_layout.addWidget(close_btn)
        
        layout.addLayout(button_layout)
