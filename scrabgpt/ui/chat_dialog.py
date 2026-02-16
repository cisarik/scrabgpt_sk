"""Chat Dialog - Konverzačné rozhranie s AI protihráčom.

Tmavé lesné Scrabble okno s animáciami:
- Loading animation (animated dots)
- Typing effect (progressive text reveal)
- Štruktúrované bubliny s drobnými políčkami pre odrážky
- User input pre voľnú komunikáciu
- Automatický scroll
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any, Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import (
    QCloseEvent,
)
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLineEdit,
    QWidget, QScrollArea, QLabel, QFrame, QProgressBar,
)

from ..ai.lmstudio_utils import get_context_stats

log = logging.getLogger("scrabgpt.ui.chat")


class ChatBubble(QFrame):
    """Jednotlivá chat bublina (user alebo AI) - cyberpunk štýl."""
    
    def __init__(
        self, 
        message: str, 
        is_user: bool = False, 
        timestamp: Optional[str] = None,
        parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.message = message
        self.is_user = is_user
        self.timestamp = timestamp or datetime.now().strftime("%H:%M:%S")
        self.message_label: QLabel | None = None
        self.accent_colors = ["#e1574f", "#f88ba8", "#5fbcbc", "#9ac7ff"]
        self._highlighted = False
        
        self._setup_ui()
    
    def _setup_ui(self) -> None:
        """Nastav UI bubliny v Scrabble tile štýle."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)
        
        self.setProperty("user", self.is_user)
        self.setStyleSheet(
            """
            QFrame {
                background: #1a241c;
                border: 1px solid #324536;
                border-radius: 8px;
                padding: 6px 8px;
            }
            QFrame[user="true"] {
                background: #233126;
                border: 1px solid #3c4d3e;
            }
            QLabel {
                color: #e8e3d9;
                font-size: 13px;
                font-family: 'Fira Sans', 'Segoe UI', sans-serif;
            }
            """
        )
        
        layout.setAlignment(Qt.AlignRight if self.is_user else Qt.AlignLeft)
        self.setMaximumWidth(420)
        
        self.body_container = QWidget()
        self.body_layout = QVBoxLayout(self.body_container)
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.body_layout.setSpacing(6)
        
        self.render_structured_content(self.message)
        layout.addWidget(self.body_container)

    def _apply_style(self) -> None:
        """Aplikuj aktuálny štýl (zohľadňuje highlight)."""
        base_bg = "#233126" if self.is_user else "#1a241c"
        base_border = "#3c4d3e" if self.is_user else "#324536"
        if self._highlighted:
            base_border = "#00ff41"
        self.setStyleSheet(
            f"""
            QFrame {{
                background: {base_bg};
                border: 1px solid {base_border};
                border-radius: 8px;
                padding: 6px 8px;
            }}
            QFrame[user="true"] {{
                background: {base_bg};
                border: 1px solid {base_border};
            }}
            QLabel {{
                color: #e8e3d9;
                font-size: 13px;
                font-family: 'Fira Sans', 'Segoe UI', sans-serif;
            }}
            """
        )
    
    def set_highlighted(self, highlighted: bool) -> None:
        """Prepni neonový highlight na poslednú bublinu."""
        self._highlighted = highlighted
        self._apply_style()
    
    def _clear_body(self) -> None:
        """Vymaž obsah bubliny."""
        while self.body_layout.count():
            item = self.body_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self.message_label = None
    
    def _body_text_style(self) -> str:
        """Základný štýl textu v bubline."""
        return (
            "color: #e8e3d9; font-size: 13px; line-height: 1.3; "
            "font-family: 'Fira Sans', 'Segoe UI', sans-serif;"
        )
    
    def set_plain_text(self, text: str) -> QLabel:
        """Zobraz jednoduchý text (použité pre typing animáciu)."""
        self._clear_body()
        label = QLabel(text)
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        label.setStyleSheet(self._body_text_style())
        self.body_layout.addWidget(label)
        self.message_label = label
        return label
    
    def render_structured_content(self, text: str) -> None:
        """Zobraz text so štruktúrou (odrážky ako malé Scrabble políčka)."""
        self._clear_body()
        bullet_index = 0
        lines = text.splitlines() or [""]
        
        for line in lines:
            stripped = line.lstrip()
            if not stripped:
                self.body_layout.addSpacing(4)
                continue
            
            if stripped.startswith(("-", "•")):
                bullet_text = stripped[1:].strip()
                row_widget = QWidget()
                row_layout = QHBoxLayout(row_widget)
                row_layout.setContentsMargins(0, 0, 0, 0)
                row_layout.setSpacing(8)
                
                bullet_color = self.accent_colors[bullet_index % len(self.accent_colors)]
                bullet_index += 1
                
                bullet_label = QLabel("•")
                bullet_label.setAlignment(Qt.AlignCenter)
                bullet_label.setFixedSize(18, 18)
                bullet_label.setStyleSheet(
                    f"background: {bullet_color}; border: 1px solid rgba(0,0,0,0.35); "
                    "border-radius: 4px; color: #0e1612; font-weight: 700; "
                    "font-size: 11px; font-family: 'Fira Sans', 'Segoe UI', sans-serif;"
                )
                
                text_label = QLabel(bullet_text or " ")
                text_label.setWordWrap(True)
                text_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
                text_label.setStyleSheet(self._body_text_style())
                
                row_layout.addWidget(bullet_label)
                row_layout.addWidget(text_label, stretch=1)
                self.body_layout.addWidget(row_widget)
            else:
                para_label = QLabel(line.strip())
                para_label.setWordWrap(True)
                para_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
                para_label.setStyleSheet(self._body_text_style())
                self.body_layout.addWidget(para_label)


class ChatDialog(QDialog):
    """Hlavný chat dialog s AI protihráčom - tmavá forest Scrabble téma.
    
    Features:
    - Loading animation (bodky)
    - Typing effect (progresívne zobrazovanie textu)
    - Chat bubliny (user vs AI)
    - Input field pre user správy
    - Automatický scroll
    """
    
    # Signals
    message_sent = Signal(str)  # Emituje sa keď user pošle správu
    
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setModal(False)  # Non-modal - môže ostať otvorené počas hry
        
        # Animation state
        self.loading_timer: Optional[QTimer] = None
        self.loading_dots = 0
        self.loading_label: Optional[QLabel] = None
        
        self.typing_timer: Optional[QTimer] = None
        self.typing_text = ""
        self.typing_position = 0
        self.typing_speed = 8  # znakov per tick
        self.typing_label: Optional[QLabel] = None
        self.typing_bubble: Optional[ChatBubble] = None
        
        # Highlight tracking
        self.last_message_bubble: Optional[ChatBubble] = None
        
        # Kontext / históriu pre tokeny
        self.chat_history: list[str] = []
        self.context_info_label: Optional[QLabel] = None
        self._context_override: tuple[int, int] | None = None  # (prompt_tokens, context_len)
        self.context_snapshot_label: Optional[QLabel] = None
        self.countdown_label: Optional[QLabel] = None
        
        # Streaming state
        self.streaming_bubble: Optional[ChatBubble] = None
        self.streaming_label: Optional[QLabel] = None
        self.streaming_text: str = ""
        self.reasoning_bubble: Optional[ChatBubble] = None
        self.reasoning_label: Optional[QLabel] = None
        self.reasoning_text: str = ""
        self.reasoning_spinner_timer: Optional[QTimer] = None
        self._reasoning_spinner_phase = 0
        
        self._setup_ui()
        self._apply_scrabble_theme()
    
    def _setup_ui(self) -> None:
        """Nastav UI komponentov v ľahkom Scrabble tile štýle."""
        self.setWindowTitle("Agent Profiling - Unified Flow")
        self.setMinimumSize(600, 700)
        self.resize(700, 800)
        
        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        # Header
        header = self._create_header()
        main_layout.addWidget(header)
        
        # Context info bar (usage of context window)
        self.context_container = QFrame()
        self.context_container.setStyleSheet("background: #0c1a12; border-bottom: 1px solid #243227;")
        self.context_container.setFixedHeight(28)
        context_layout = QHBoxLayout(self.context_container)
        context_layout.setContentsMargins(12, 0, 12, 0)
        context_layout.setSpacing(10)

        self.context_label = QLabel("Context Window:")
        self.context_label.setStyleSheet("color: #5fbcbc; font-size: 10px; font-family: 'Fira Code'; font-weight: bold;")
        context_layout.addWidget(self.context_label)

        self.context_bar = QProgressBar()
        self.context_bar.setRange(0, 100)
        self.context_bar.setValue(0)
        self.context_bar.setTextVisible(True)
        self.context_bar.setAlignment(Qt.AlignCenter)
        self.context_bar.setStyleSheet("""
            QProgressBar {
                background: #1a241c;
                border: 1px solid #324536;
                border-radius: 4px;
                color: #e8e3d9;
                height: 14px;
                font-size: 9px;
                font-family: 'Fira Code';
            }
            QProgressBar::chunk {
                background: #5fbcbc;
                border-radius: 3px;
            }
        """)
        context_layout.addWidget(self.context_bar, stretch=1)
        
        self.token_info_label = QLabel("0 / 0 tokens")
        self.token_info_label.setStyleSheet("color: #80cbc4; font-size: 10px; font-family: 'Fira Code';")
        context_layout.addWidget(self.token_info_label)

        main_layout.addWidget(self.context_container)
        
        # Chat area (scrollable) - tmavé plátno
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("""
            QScrollArea {
                background: #0f1812;
                border: none;
            }
            QScrollBar:vertical {
                background: #0b120d;
                width: 10px;
                border: 1px solid #243227;
                border-radius: 5px;
            }
            QScrollBar::handle:vertical {
                background: #3a4c3d;
                min-height: 24px;
                border-radius: 4px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                border: none;
                background: none;
            }
        """)
        
        # Chat container
        self.chat_container = QWidget()
        self.chat_layout = QVBoxLayout(self.chat_container)
        self.chat_layout.setAlignment(Qt.AlignTop)
        self.chat_layout.setSpacing(10)
        self.chat_layout.setContentsMargins(14, 14, 14, 14)
        
        scroll.setWidget(self.chat_container)
        main_layout.addWidget(scroll, stretch=1)
        
        # Countdown (timeout) label
        self.countdown_label = QLabel("")
        self.countdown_label.setVisible(False)
        self.countdown_label.setStyleSheet(
            "color: #ffb74d; background: #1a1208; border: 1px solid #ffb74d; "
            "border-radius: 6px; padding: 4px 8px; font-family: 'Fira Code', 'Consolas'; "
            "font-size: 11px;"
        )
        main_layout.addWidget(self.countdown_label)
        
        # Input area
        input_area = self._create_input_area()
        main_layout.addWidget(input_area)
    
    def _create_header(self) -> QWidget:
        """Vytvor header v štýle drevenej lišty."""
        header = QFrame()
        header.setFixedHeight(50)
        header.setStyleSheet("""
            QFrame {
                background: #2b3c2f;
                border-bottom: 1px solid #1d2a21;
            }
        """)
        
        layout = QHBoxLayout(header)
        layout.setContentsMargins(12, 8, 12, 8)
        
        # Title - messenger icon + text
        title = QLabel("💬 Agent Profiling")
        title.setStyleSheet("""
            color: #e8e3d9;
            font-size: 13px;
            font-weight: bold;
            font-family: 'Fira Sans', 'Segoe UI', sans-serif;
        """)
        layout.addWidget(title)
        
        layout.addStretch()
        
        # Status indicator - neónový zelený
        self.status_label = QLabel("● messenger")
        self.status_label.setStyleSheet("""
            background: #4b7d5d;
            color: #f0f6f0;
            padding: 4px 8px;
            border-radius: 10px;
            font-size: 10px;
            font-family: 'Fira Sans', 'Segoe UI', sans-serif;
        """)
        layout.addWidget(self.status_label)
        
        # Close button - minimalistický
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(24, 24)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #2b241a;
                font-size: 16px;
                border: none;
            }
            QPushButton:hover {
                color: #e1574f;
                background: rgba(43,36,26,0.08);
            }
        """)
        close_btn.clicked.connect(self.hide)
        layout.addWidget(close_btn)
        
        return header
    
    def _create_input_area(self) -> QWidget:
        """Vytvor input area v odtieni hracej dosky."""
        input_frame = QFrame()
        input_frame.setFixedHeight(70)
        input_frame.setStyleSheet("""
            QFrame {
                background: #151f18;
                border-top: 1px solid #243227;
            }
        """)
        
        layout = QHBoxLayout(input_frame)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(10)
        
        # Input field - cyberpunk štýl s neónovým borderom
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Napíš správu AI protihráčovi...")
        self.input_field.setStyleSheet("""
            QLineEdit {
                background: #0f1812;
                color: #e8e3d9;
                border: 1px solid #324536;
                border-radius: 6px;
                padding: 10px;
                font-size: 12px;
                font-family: 'Fira Sans', 'Segoe UI', sans-serif;
            }
            QLineEdit:focus {
                border: 1px solid #5fbcbc;
                background: #132119;
            }
            QLineEdit::placeholder {
                color: #6f7a6d;
            }
        """)
        self.input_field.returnPressed.connect(self._send_message)
        layout.addWidget(self.input_field, stretch=1)
        
        # Send button - neónový zelený s hover efektom
        send_btn = QPushButton("Odoslať")
        send_btn.setFixedSize(90, 40)
        send_btn.setCursor(Qt.PointingHandCursor)
        send_btn.setStyleSheet("""
            QPushButton {
                background: #d64b3e;
                color: #fdfbf5;
                border: 1px solid #9f332c;
                border-radius: 6px;
                font-size: 11px;
                font-weight: 700;
                font-family: 'Fira Sans', 'Segoe UI', sans-serif;
            }
            QPushButton:hover {
                background: #f88ba8;
                color: #0e1612;
                border: 1px solid #c3564f;
            }
            QPushButton:pressed {
                background: #b63b31;
            }
        """)
        send_btn.clicked.connect(self._send_message)
        layout.addWidget(send_btn)
        
        return input_frame
    
    def _apply_scrabble_theme(self) -> None:
        """Aplikuj tmavú lesnú Scrabble tému na celé okno."""
        self.setStyleSheet("""
            QDialog {
                background: #0e1612;
                border: 1px solid #243227;
            }
        """)
    
    def _send_message(self) -> None:
        """Odošli user správu."""
        text = self.input_field.text().strip()
        if not text:
            return
        
        # Pridaj user bublinu
        self.add_user_message(text)
        
        # Emit signal
        self.message_sent.emit(text)
        
        # Clear input
        self.input_field.clear()
        
        # Show loading animation
        self._show_loading_animation()
    
    def add_user_message(self, message: str) -> None:
        """Pridaj user správu do chatu."""
        bubble = ChatBubble(message, is_user=True)
        self.chat_layout.addWidget(bubble, alignment=Qt.AlignRight)
        self._highlight_bubble(bubble)
        self.chat_history.append(message)
        self._render_context_info()
        self._scroll_to_bottom()
        log.debug("User message added: %s", message[:50])
    
    def add_ai_message(self, message: str, *, use_typing_effect: bool = False) -> None:
        """Pridaj AI správu do chatu (default bez typing efektu)."""
        self._hide_loading_animation()
        
        if use_typing_effect:
            # Vytvor prázdnu bublinu a postupne naplň
            bubble = ChatBubble("", is_user=False)
            self.chat_layout.addWidget(bubble, alignment=Qt.AlignLeft)
            self._highlight_bubble(bubble)
            self._scroll_to_bottom()
            
            # Spusti typing animation
            self._start_typing_animation(message, bubble)
        else:
            # Priamy display bez animácie
            bubble = ChatBubble(message, is_user=False)
            self.chat_layout.addWidget(bubble, alignment=Qt.AlignLeft)
            self._highlight_bubble(bubble)
            self._scroll_to_bottom()
        
        self.chat_history.append(message)
        self._render_context_info()
        
        log.debug("AI message added: %s", message[:50])

    def add_error_message(self, message: str) -> None:
        """Pridaj chybovú správu (červená bublina)."""
        bubble = ChatBubble(message, is_user=False)
        bubble.setStyleSheet(
            "QFrame { background: #2a0e0e; border: 1px solid #ff5c5c; border-radius: 8px; padding: 6px 8px; }"
            "QLabel { color: #ffb3b3; font-size: 13px; font-family: 'Fira Sans', 'Segoe UI', sans-serif; }"
        )
        self.chat_layout.addWidget(bubble, alignment=Qt.AlignLeft)
        self._highlight_bubble(bubble)
        self.chat_history.append(message)
        self._render_context_info()
        self._scroll_to_bottom()

    def _highlight_bubble(self, bubble: ChatBubble) -> None:
        """Označ poslednú pridanú bublinu neonovým lemom."""
        if self.last_message_bubble and self.last_message_bubble is not bubble:
            self.last_message_bubble.set_highlighted(False)
        bubble.set_highlighted(True)
        self.last_message_bubble = bubble

    def _render_context_info(self) -> None:
        """Zobraz info o context window pre celú konverzáciu."""
        model_key = os.getenv("OPENAI_MODEL") or os.getenv("LLMSTUDIO_MODEL")
        aggregate_history = list(self.chat_history)
        if self.streaming_text:
            aggregate_history.append(self.streaming_text)
        if self._context_override:
            tokens_used, ctx_len = self._context_override
            percent = (tokens_used / ctx_len * 100.0) if ctx_len > 0 else 0.0
        else:
            tokens_used, ctx_len, percent = get_context_stats(aggregate_history, model_key)
        
        # Update progress bar
        if tokens_used <= 0 or ctx_len <= 0:
            self.context_bar.setValue(0)
            self.token_info_label.setText("Unknown context")
            return
        
        used_pct = int(percent)
        self.context_bar.setValue(used_pct)
        self.context_bar.setFormat(f"{used_pct}% used")
        
        # Update tokens label
        self.token_info_label.setText(f"{tokens_used} / {ctx_len} tokens")
        
        # Warning color if nearly full
        if used_pct > 90:
            self.token_info_label.setStyleSheet("color: #ff5c5c; font-size: 10px; font-family: 'Fira Code'; font-weight: bold;")
        else:
            self.token_info_label.setStyleSheet("color: #80cbc4; font-size: 10px; font-family: 'Fira Code';")

    def update_context_usage(self, prompt_tokens: int, context_length: int) -> None:
        """Externé nastavenie usage (napr. z LMStudio usage)."""
        self._context_override = (prompt_tokens, context_length)
        self._render_context_info()

    def _update_reasoning_spinner(self) -> None:
        """Animuj ⏳ počas reasoning streamu."""
        if not self.reasoning_label:
            return
        frames = ["⏳", "⌛"]
        frame = frames[self._reasoning_spinner_phase % len(frames)]
        self._reasoning_spinner_phase += 1
        # Keep existing text without cursor if any
        base = self.reasoning_text if self.reasoning_text else ""
        if base:
            self.reasoning_label.setText(f"{frame} {base}▋")
        else:
            self.reasoning_label.setText(frame)

    def set_context_snapshot(self, text: str) -> None:
        """Zobrazí snapshot celého kontextu (prompt + históriu)."""
        if self.context_snapshot_label:
            self.chat_layout.removeWidget(self.context_snapshot_label)
            self.context_snapshot_label.deleteLater()
            self.context_snapshot_label = None
        if not text.strip():
            return
        
        label = QLabel(text)
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        label.setStyleSheet(
            "color: #d7e4d8; background: #0b1410; border: 1px solid #2f5c39; "
            "border-radius: 6px; padding: 8px 10px; font-family: 'Fira Code', 'Consolas'; "
            "font-size: 11px;"
        )
        self.context_snapshot_label = label
        self.chat_layout.addWidget(label, alignment=Qt.AlignLeft)

    def add_debug_message(self, message: str) -> None:
        """Pridá debug/info blok (napr. celý prompt/odpoveď LLM)."""
        label = QLabel(message)
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        label.setStyleSheet(
            "color: #9ac7ff; background: #0d1620; border: 1px solid #3a4c63; "
            "border-radius: 6px; padding: 6px 10px; font-family: 'Fira Code', 'Consolas'; "
            "font-size: 11px;"
        )
        self.chat_layout.addWidget(label, alignment=Qt.AlignLeft)
        self._scroll_to_bottom()

    def add_profiling_info(self, title: str, data: dict[str, str]) -> None:
        """Pridá štruktúrovaný profiling blok (napr. stav racku, tools)."""
        container = QFrame()
        container.setStyleSheet(
            "background: #0d1620; border: 1px solid #3a4c63; border-radius: 6px;"
        )
        layout = QVBoxLayout(container)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)
        
        header = QLabel(f"📊 {title}")
        header.setStyleSheet("color: #9ac7ff; font-weight: bold; font-size: 12px; font-family: 'Fira Sans', sans-serif;")
        layout.addWidget(header)
        
        # Content container - use simple vertical list but with better styling
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(4, 0, 0, 0)
        content_layout.setSpacing(4)
        
        for key, value in data.items():
            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(8)
            
            key_label = QLabel(f"{key}:")
            key_label.setStyleSheet("color: #5fbcbc; font-weight: bold; font-size: 11px; font-family: 'Fira Code', monospace;")
            key_label.setFixedWidth(120) # Align keys
            
            val_label = QLabel(str(value))
            val_label.setStyleSheet("color: #d7e4d8; font-size: 11px; font-family: 'Fira Code', monospace;")
            val_label.setWordWrap(True)
            
            row_layout.addWidget(key_label)
            row_layout.addWidget(val_label, stretch=1)
            content_layout.addWidget(row_widget)
            
        layout.addWidget(content_widget)
        self.chat_layout.addWidget(container, alignment=Qt.AlignLeft)
        self._scroll_to_bottom()

    def add_tool_call(self, tool_name: str, args: dict | str) -> None:
        """Zobrazí volanie interného nástroja."""
        container = QFrame()
        container.setStyleSheet(
            "background: #1a1208; border-left: 3px solid #ffb74d; border-radius: 4px;"
        )
        container.setMinimumWidth(450)  # Prevent squashing
        layout = QVBoxLayout(container)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)
        
        header_layout = QHBoxLayout()
        header_layout.setSpacing(8)
        
        icon = QLabel("🛠️")
        name_label = QLabel(f"Calling: {tool_name}")
        name_label.setStyleSheet("color: #ffb74d; font-weight: bold; font-family: 'Fira Code', monospace; font-size: 11px;")
        
        header_layout.addWidget(icon)
        header_layout.addWidget(name_label, stretch=1)
        layout.addLayout(header_layout)
        
        # Args display - verbose JSON
        import json
        arg_str = json.dumps(args, ensure_ascii=False, indent=2) if isinstance(args, dict) else str(args)
        arg_label = QLabel(arg_str)
        # Preserve newlines for JSON pretty print
        arg_label.setTextFormat(Qt.PlainText)
        arg_label.setStyleSheet("color: #d7e4d8; font-family: 'Fira Code', monospace; font-size: 10px; padding-left: 24px;")
        layout.addWidget(arg_label)
        
        self.chat_layout.addWidget(container, alignment=Qt.AlignLeft)
        self._scroll_to_bottom()

    def add_tool_result(self, tool_name: str, result: Any, is_error: bool = False) -> None:
        """Zobrazí výsledok volania nástroja."""
        container = QFrame()
        color = "#ff5c5c" if is_error else "#00ff41"
        bg = "#2a0e0e" if is_error else "#0c1a12"
        
        container.setStyleSheet(
            f"background: {bg}; border-left: 3px solid {color}; border-radius: 4px;"
        )
        container.setMinimumWidth(450)  # Prevent squashing
        layout = QVBoxLayout(container)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)
        
        header_layout = QHBoxLayout()
        icon = QLabel("❌" if is_error else "✅")
        title = QLabel(f"{tool_name} -> {'Error' if is_error else 'Result'}")
        title.setStyleSheet(f"color: {color}; font-weight: bold; font-family: 'Fira Code', monospace; font-size: 11px;")
        
        header_layout.addWidget(icon)
        header_layout.addWidget(title, stretch=1)
        layout.addLayout(header_layout)
        
        import json
        res_str = json.dumps(result, ensure_ascii=False, indent=2) if isinstance(result, (dict, list)) else str(result)
        
        # Only truncate extremely long responses, let user see full JSON mostly
        if len(res_str) > 2000:
            res_str = res_str[:2000] + "... (truncated)"
            
        res_label = QLabel(res_str)
        res_label.setTextFormat(Qt.PlainText)
        res_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        res_label.setStyleSheet("color: #d7e4d8; font-family: 'Fira Code', monospace; font-size: 10px; padding-left: 24px;")
        layout.addWidget(res_label)
        
        self.chat_layout.addWidget(container, alignment=Qt.AlignLeft)
        self._scroll_to_bottom()

    def add_agent_activity(self, message: str) -> None:
        """Pridá malú informačnú správu o aktivite agenta (napr. volanie nástroja)."""
        label = QLabel(message)
        label.setWordWrap(True)
        label.setStyleSheet(
            "color: #80cbc4; font-size: 11px; font-family: 'Fira Code', 'Consolas'; "
            "padding: 2px 4px; font-style: italic;"
        )
        self.chat_layout.addWidget(label, alignment=Qt.AlignLeft)
        self._scroll_to_bottom()

    def update_countdown(self, seconds_remaining: int) -> None:
        """Aktualizuje odpočet timeoutu."""
        if self.countdown_label is None:
            return
        if seconds_remaining <= 0:
            self.countdown_label.setVisible(False)
            return
        minutes = seconds_remaining // 60
        secs = seconds_remaining % 60
        self.countdown_label.setText(f"⏳ {minutes:02d}:{secs:02d}")
        self.countdown_label.setVisible(True)
    
    def _show_loading_animation(self) -> None:
        """Zobraz loading animation v cyberpunk štýle."""
        if self.loading_label is None:
            self.loading_label = QLabel("⚙️ AI premýšľa")
            self.loading_label.setStyleSheet("""
                color: #0e1612;
                font-size: 11px;
                font-style: italic;
                font-family: 'Fira Sans', 'Segoe UI', sans-serif;
                padding: 6px 10px;
                background: #00ff41;
                border: 1px solid #00ff41;
                border-radius: 6px;
            """)
            self.chat_layout.addWidget(self.loading_label, alignment=Qt.AlignLeft)
        
        self.loading_dots = 0
        
        if self.loading_timer is None:
            self.loading_timer = QTimer(self)
            self.loading_timer.timeout.connect(self._update_loading_animation)
        
        self.loading_timer.start(400)  # 400ms per update
        self._scroll_to_bottom()
        
        log.debug("Loading animation started")
    
    def _update_loading_animation(self) -> None:
        """Update loading animation (cycle through dots)."""
        if self.loading_label is None:
            return
        
        dots = "." * (self.loading_dots % 4)
        self.loading_label.setText(f"⚙️ AI premýšľa{dots}")
        
        self.loading_dots += 1
    
    def _hide_loading_animation(self) -> None:
        """Skry loading animation."""
        if self.loading_timer:
            self.loading_timer.stop()
        
        if self.loading_label:
            self.chat_layout.removeWidget(self.loading_label)
            self.loading_label.deleteLater()
            self.loading_label = None
        
        log.debug("Loading animation hidden")
    
    def _start_typing_animation(self, text: str, bubble: ChatBubble) -> None:
        """Spusti typing effect pre AI odpoveď."""
        self.typing_text = text
        self.typing_position = 0
        self.typing_bubble = bubble
        self.typing_label = bubble.set_plain_text("")  # Dočasný text pre animáciu
        
        if self.typing_timer is None:
            self.typing_timer = QTimer(self)
            self.typing_timer.timeout.connect(self._update_typing_animation)
        
        self.typing_timer.start(20)  # 20ms per update (smooth)
        
        log.debug("Typing animation started (text_len=%d)", len(text))
    
    def _update_typing_animation(self) -> None:
        """Update typing animation (reveal characters progressively)."""
        if self.typing_label is None or not self.typing_text:
            self._stop_typing_animation()
            return
        
        # Pridaj N znakov
        chars_to_add = min(self.typing_speed, len(self.typing_text) - self.typing_position)
        self.typing_position += chars_to_add
        
        # Update label s cursor
        revealed_text = self.typing_text[:self.typing_position]
        
        if self.typing_position < len(self.typing_text):
            # Stále píše - zobraz cursor
            self.typing_label.setText(revealed_text + "▋")
        else:
            # Dokončené - odstráň cursor
            self.typing_label.setText(revealed_text)
            self._stop_typing_animation(finalize=True)
        
        self._scroll_to_bottom()
    
    def _stop_typing_animation(self, finalize: bool = False) -> None:
        """Zastav typing animation."""
        if self.typing_timer:
            self.typing_timer.stop()
        
        bubble = self.typing_bubble
        final_text = self.typing_text
        self.typing_text = ""
        self.typing_position = 0
        self.typing_label = None
        self.typing_bubble = None
        
        if finalize and bubble and final_text:
            bubble.render_structured_content(final_text)
            self.chat_history.append(final_text)
            self._render_context_info()
        
        log.debug("Typing animation stopped")

    # ---------- Streaming API output ----------
    def start_streaming_ai_message(self) -> None:
        """Priprav prázdnu bublinu na prichádzajúce tokeny."""
        self._hide_loading_animation()
        self.streaming_text = ""
        bubble = ChatBubble("", is_user=False)
        self.chat_layout.addWidget(bubble, alignment=Qt.AlignLeft)
        self._highlight_bubble(bubble)
        self.streaming_bubble = bubble
        self.streaming_label = bubble.set_plain_text("")
        self._scroll_to_bottom()
    
    def start_reasoning_stream(self) -> None:
        """Priprav blok pre reasoning (thinking) stream."""
        self.reasoning_text = ""
        bubble = ChatBubble("", is_user=False)
        # Styling for thinking block - full width, code font
        bubble.setStyleSheet(
            "QFrame { background: #0b1410; border: 1px dashed #5fbcbc; border-radius: 8px; padding: 8px 12px; }"
            "QLabel { color: #9ee6aa; font-size: 12px; font-family: 'Fira Code', 'Consolas'; }"
        )
        bubble.setMinimumWidth(500) # Ensure wide enough for code
        
        self.chat_layout.addWidget(bubble, alignment=Qt.AlignLeft)
        self.reasoning_bubble = bubble
        self.reasoning_label = bubble.set_plain_text("⏳ ")
        self.reasoning_label.setTextFormat(Qt.PlainText) # Ensure whitespace preserved
        
        # Spinner timer for ⏳ animation
        if self.reasoning_spinner_timer is None:
            self.reasoning_spinner_timer = QTimer(self)
            self.reasoning_spinner_timer.setInterval(450)
            self.reasoning_spinner_timer.timeout.connect(self._update_reasoning_spinner)
        self._reasoning_spinner_phase = 0
        self.reasoning_spinner_timer.start()
        self._scroll_to_bottom()
    
    def update_streaming_ai_message(self, delta: str) -> None:
        """Pridaj streamujúci text do bubliny."""
        if not delta:
            return
        if self.streaming_label is None:
            self.start_streaming_ai_message()
        self.streaming_text += delta
        if self.streaming_label:
            self.streaming_label.setText(self.streaming_text + "▋")
        # Priebežne aktualizuj context bar podľa streamu
        self._render_context_info()
        self._scroll_to_bottom()
    
    def update_reasoning_stream(self, delta: str) -> None:
        """Pridaj reasoning tokeny do reasoning bubliny."""
        if not delta:
            return
        if self.reasoning_label is None:
            self.start_reasoning_stream()
        
        self.reasoning_text += delta
        
        # Update label - preserve formatting
        if self.reasoning_label:
            header = "💭 Thinking Process:\n\n"
            self.reasoning_label.setText(header + self.reasoning_text + "▋")
            
        self._scroll_to_bottom()

    def finish_streaming_ai_message(self) -> None:
        """Ukonči streaming, vykresli štruktúru a aktualizuj context info."""
        if self.streaming_bubble and self.streaming_text:
            self.streaming_bubble.render_structured_content(self.streaming_text)
            self.chat_history.append(self.streaming_text)
            self._render_context_info()
        if self.streaming_label:
            self.streaming_label = None
        self.streaming_bubble = None
        self.streaming_text = ""
        # Reasoning stream finish (optional)
        if self.reasoning_bubble:
            if self.reasoning_text:
                self.reasoning_bubble.render_structured_content(self.reasoning_text)
            self.reasoning_bubble = None
            self.reasoning_label = None
            self.reasoning_text = ""
        if self.reasoning_spinner_timer:
            self.reasoning_spinner_timer.stop()
    
    def _scroll_to_bottom(self) -> None:
        """Automaticky scrolluj na koniec chatu."""
        # Find scroll area
        scroll = self.findChild(QScrollArea)
        if scroll:
            scroll.verticalScrollBar().setValue(
                scroll.verticalScrollBar().maximum()
            )
    
    def closeEvent(self, event: QCloseEvent) -> None:
        """Cleanup timers on close."""
        if self.loading_timer:
            self.loading_timer.stop()
        if self.typing_timer:
            self.typing_timer.stop()
        
        # Don't actually close, just hide
        event.ignore()
        self.hide()
        
        log.debug("Chat dialog hidden")
    
    def showEvent(self, event) -> None:
        """Auto-focus input field when shown."""
        super().showEvent(event)
        self.input_field.setFocus()
