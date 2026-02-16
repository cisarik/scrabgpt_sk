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
    QShowEvent,
)
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLineEdit,
    QWidget, QScrollArea, QLabel, QFrame, QProgressBar,
)

from ..ai.lmstudio_utils import get_context_stats

log = logging.getLogger("scrabgpt.ui.chat")

# Qt enum aliases for mypy-friendly typing with PySide6 stubs.
ALIGN_LEFT = Qt.AlignmentFlag.AlignLeft
ALIGN_RIGHT = Qt.AlignmentFlag.AlignRight
ALIGN_TOP = Qt.AlignmentFlag.AlignTop
ALIGN_CENTER = Qt.AlignmentFlag.AlignCenter
ALIGN_HCENTER = Qt.AlignmentFlag.AlignHCenter
SCROLLBAR_ALWAYS_OFF = Qt.ScrollBarPolicy.ScrollBarAlwaysOff
POINTING_HAND_CURSOR = Qt.CursorShape.PointingHandCursor
TEXT_SELECTABLE_BY_MOUSE = Qt.TextInteractionFlag.TextSelectableByMouse
PLAIN_TEXT = Qt.TextFormat.PlainText


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
        
        layout.setAlignment(ALIGN_RIGHT if self.is_user else ALIGN_LEFT)
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
        label.setTextInteractionFlags(TEXT_SELECTABLE_BY_MOUSE)
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
                bullet_label.setAlignment(ALIGN_CENTER)
                bullet_label.setFixedSize(18, 18)
                bullet_label.setStyleSheet(
                    f"background: {bullet_color}; border: 1px solid rgba(0,0,0,0.35); "
                    "border-radius: 4px; color: #0e1612; font-weight: 700; "
                    "font-size: 11px; font-family: 'Fira Sans', 'Segoe UI', sans-serif;"
                )
                
                text_label = QLabel(bullet_text or " ")
                text_label.setWordWrap(True)
                text_label.setTextInteractionFlags(TEXT_SELECTABLE_BY_MOUSE)
                text_label.setStyleSheet(self._body_text_style())
                
                row_layout.addWidget(bullet_label)
                row_layout.addWidget(text_label, stretch=1)
                self.body_layout.addWidget(row_widget)
            else:
                para_label = QLabel(line.strip())
                para_label.setWordWrap(True)
                para_label.setTextInteractionFlags(TEXT_SELECTABLE_BY_MOUSE)
                para_label.setStyleSheet(self._body_text_style())
                self.body_layout.addWidget(para_label)


class SectionFeedCard(QFrame):
    """Sekcia feedu s hlavičkou a zoznamom krokov."""

    def __init__(
        self,
        *,
        title: str,
        icon: str,
        subtitle: str,
        accent: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._accent = accent
        self._entry_labels_by_key: dict[str, QLabel] = {}
        self._entry_count = 0
        self._setup_ui(title=title, icon=icon, subtitle=subtitle)

    def _setup_ui(self, *, title: str, icon: str, subtitle: str) -> None:
        self.setStyleSheet(
            """
            QFrame {
                background: #111b14;
                border: 1px solid #2f5c39;
                border-radius: 10px;
                padding: 0;
            }
            QLabel#SectionTitle {
                color: #e9f5ea;
                font-size: 13px;
                font-weight: 700;
                font-family: 'Fira Sans', 'Segoe UI', sans-serif;
            }
            QLabel#SectionSubtitle {
                color: #9cc8a0;
                font-size: 10px;
                font-family: 'Fira Sans', 'Segoe UI', sans-serif;
            }
            """
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 10)
        layout.setSpacing(8)

        header = QFrame()
        header.setStyleSheet(
            f"QFrame {{ background: #132119; border: 1px solid {self._accent}; border-radius: 8px; }}"
        )
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(8, 6, 8, 6)
        header_layout.setSpacing(2)

        title_label = QLabel(f"{icon} {title}")
        title_label.setObjectName("SectionTitle")
        header_layout.addWidget(title_label)

        subtitle_label = QLabel(subtitle)
        subtitle_label.setObjectName("SectionSubtitle")
        subtitle_label.setWordWrap(True)
        header_layout.addWidget(subtitle_label)
        layout.addWidget(header)

        self.entries_widget = QWidget()
        self.entries_layout = QVBoxLayout(self.entries_widget)
        self.entries_layout.setContentsMargins(2, 2, 2, 2)
        self.entries_layout.setSpacing(6)
        layout.addWidget(self.entries_widget)

    def append_entry(self, message: str, *, merge_key: str | None = None) -> tuple[QLabel, bool]:
        """Pridá (alebo aktualizuje) riadok v sekcii."""
        if merge_key and merge_key in self._entry_labels_by_key:
            label = self._entry_labels_by_key[merge_key]
            label.setText(message)
            return label, True

        self._entry_count += 1
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(8)

        step_label = QLabel(f"{self._entry_count}.")
        step_label.setFixedWidth(24)
        step_label.setAlignment(ALIGN_TOP | ALIGN_RIGHT)
        step_label.setStyleSheet(
            f"color: {self._accent}; font-size: 11px; font-weight: 700; font-family: 'Fira Code', 'Consolas';"
        )
        row_layout.addWidget(step_label)

        text_label = QLabel(message)
        text_label.setWordWrap(True)
        text_label.setTextInteractionFlags(TEXT_SELECTABLE_BY_MOUSE)
        text_label.setStyleSheet(
            "color: #d6ead8; font-size: 12px; line-height: 1.35; font-family: 'Fira Sans', 'Segoe UI', sans-serif;"
        )
        row_layout.addWidget(text_label, stretch=1)

        self.entries_layout.addWidget(row)
        if merge_key:
            self._entry_labels_by_key[merge_key] = text_label
        return text_label, False


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
    _SECTION_META: dict[str, tuple[str, str, str, str]] = {
        "planning": (
            "Plánovanie",
            "🧭",
            "Modely pripravujú kandidátov a skúšajú stratégie ťahu.",
            "#7cc4ff",
        ),
        "word_check": (
            "Kontrola slov",
            "📚",
            "Kontrola slovníka, legality a rozhodcu pre navrhnuté slová.",
            "#7fe39b",
        ),
        "scoring": (
            "Skórovanie",
            "🧮",
            "Výpočet bodov a porovnanie bodových variantov.",
            "#ffd166",
        ),
        "final": (
            "Finálny výber",
            "🏁",
            "Výber finálneho ťahu, fallbacky a aplikovanie výsledku.",
            "#f78c6b",
        ),
    }
    
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
        self._pending_tool_calls: list[tuple[str, dict[str, Any] | str, str | None]] = []
        self._last_activity_merge_key: str | None = None
        self._last_activity_bubble: ChatBubble | None = None
        self._last_activity_history_index: int | None = None
        self._word_validation_state: dict[str, dict[str, Any]] = {}
        self._active_sections: dict[str, SectionFeedCard] = {}
        self._section_history_indices: dict[tuple[str, str], int] = {}
        self._turn_index = 0
        self._turn_sections_ready = False
        
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
        self.context_bar.setAlignment(ALIGN_CENTER)
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
        scroll.setHorizontalScrollBarPolicy(SCROLLBAR_ALWAYS_OFF)
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
        self.chat_layout.setAlignment(ALIGN_TOP)
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
        close_btn.setCursor(POINTING_HAND_CURSOR)
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
        send_btn.setCursor(POINTING_HAND_CURSOR)
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
        self._reset_activity_merge_state()
        bubble = ChatBubble(message, is_user=True)
        self.chat_layout.addWidget(bubble, alignment=ALIGN_RIGHT)
        self._highlight_bubble(bubble)
        self.chat_history.append(message)
        self._render_context_info()
        self._scroll_to_bottom()
        log.debug("User message added: %s", message[:50])
    
    def add_ai_message(self, message: str, *, use_typing_effect: bool = False) -> None:
        """Pridaj AI správu do chatu (default bez typing efektu)."""
        self._hide_loading_animation()
        self._reset_activity_merge_state()
        
        if use_typing_effect:
            # Vytvor prázdnu bublinu a postupne naplň
            bubble = ChatBubble("", is_user=False)
            self.chat_layout.addWidget(bubble, alignment=ALIGN_LEFT)
            self._highlight_bubble(bubble)
            self._scroll_to_bottom()
            
            # Spusti typing animation
            self._start_typing_animation(message, bubble)
        else:
            # Priamy display bez animácie
            bubble = ChatBubble(message, is_user=False)
            self.chat_layout.addWidget(bubble, alignment=ALIGN_LEFT)
            self._highlight_bubble(bubble)
            self._scroll_to_bottom()
        
        self.chat_history.append(message)
        self._render_context_info()
        
        log.debug("AI message added: %s", message[:50])

    def add_error_message(self, message: str) -> None:
        """Pridaj chybovú správu (červená bublina)."""
        self._reset_activity_merge_state()
        bubble = ChatBubble(message, is_user=False)
        bubble.setStyleSheet(
            "QFrame { background: #2a0e0e; border: 1px solid #ff5c5c; border-radius: 8px; padding: 6px 8px; }"
            "QLabel { color: #ffb3b3; font-size: 13px; font-family: 'Fira Sans', 'Segoe UI', sans-serif; }"
        )
        self.chat_layout.addWidget(bubble, alignment=ALIGN_LEFT)
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

    def _reset_activity_merge_state(self) -> None:
        """Reset merge state pre agregačné chat eventy."""
        self._last_activity_merge_key = None
        self._last_activity_bubble = None
        self._last_activity_history_index = None

    @staticmethod
    def _normalize_section(section: str | None) -> str | None:
        if not section:
            return None
        normalized = section.strip().lower().replace(" ", "_")
        aliases = {
            "planovanie": "planning",
            "planning": "planning",
            "kontrola_slov": "word_check",
            "word_check": "word_check",
            "wordcheck": "word_check",
            "slovnik": "word_check",
            "slovnik_check": "word_check",
            "skorovanie": "scoring",
            "scoring": "scoring",
            "final": "final",
            "finalny_vyber": "final",
            "final_choice": "final",
        }
        return aliases.get(normalized, normalized)

    def _start_new_turn_sections(self) -> None:
        """Inicializuje nové sekcie pre ďalší AI ťah."""
        self._turn_index += 1
        self._active_sections.clear()
        self._section_history_indices.clear()
        self._turn_sections_ready = True

        banner = QLabel(
            f"🎯 Ťah AI #{self._turn_index} • {datetime.now().strftime('%H:%M:%S')}"
        )
        banner.setStyleSheet(
            "color: #dcefdc; background: #102017; border: 1px solid #2f5c39; "
            "border-radius: 8px; padding: 6px 10px; font-size: 11px; font-weight: 700; "
            "font-family: 'Fira Sans', 'Segoe UI', sans-serif;"
        )
        self.chat_layout.addWidget(banner, alignment=ALIGN_HCENTER)
        self.chat_history.append(f"AI turn {self._turn_index} started")
        self._render_context_info()
        self._scroll_to_bottom()

    def _ensure_section_card(self, section_key: str) -> SectionFeedCard:
        normalized = self._normalize_section(section_key) or "planning"
        if normalized not in self._SECTION_META:
            normalized = "planning"

        existing = self._active_sections.get(normalized)
        if existing is not None:
            return existing

        title, icon, subtitle, accent = self._SECTION_META[normalized]
        card = SectionFeedCard(
            title=title,
            icon=icon,
            subtitle=subtitle,
            accent=accent,
            parent=self.chat_container,
        )
        self.chat_layout.addWidget(card)
        self._active_sections[normalized] = card
        return card

    def _section_for_tool(self, normalized_tool: str) -> str:
        if normalized_tool in {
            "validate_word_slovak",
            "validate_word_english",
            "rules_extract_all_words",
            "validate_move_legality",
        }:
            return "word_check"
        if normalized_tool in {"calculate_move_score", "scoring_score_words"}:
            return "scoring"
        if normalized_tool in {"get_board_state", "get_rack_letters"}:
            return "planning"
        return "planning"

    def _infer_activity_section(self, message: str, merge_key: str | None = None) -> str:
        key_lower = (merge_key or "").lower()
        if key_lower.startswith("tool:"):
            tool_part = key_lower.split(":", 2)[1] if ":" in key_lower else ""
            return self._section_for_tool(tool_part)

        lowered = message.lower()
        final_markers = (
            "víťaz",
            "odohrala",
            "aplik",
            "fallback",
            "žiadne návrhy",
            "mení písmená",
            "timeout",
            "api chyba",
            "kandidát",
            "final",
        )
        if any(marker in lowered for marker in final_markers):
            return "final"

        scoring_markers = ("skóre", "score", "bodov", "bod")
        if any(marker in lowered for marker in scoring_markers):
            return "scoring"

        check_markers = (
            "slovník",
            "overenie",
            "overujem",
            "rozhodca",
            "legalita",
            "slová",
            "neplatné slovo",
        )
        if any(marker in lowered for marker in check_markers):
            return "word_check"

        return "planning"

    def reset_tool_tracking(self) -> None:
        """Vyčistí stav nástrojov na nový AI ťah."""
        self._pending_tool_calls.clear()
        self._word_validation_state.clear()
        self._reset_activity_merge_state()
        self._start_new_turn_sections()

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
        label.setTextInteractionFlags(TEXT_SELECTABLE_BY_MOUSE)
        label.setStyleSheet(
            "color: #d7e4d8; background: #0b1410; border: 1px solid #2f5c39; "
            "border-radius: 6px; padding: 8px 10px; font-family: 'Fira Code', 'Consolas'; "
            "font-size: 11px;"
        )
        self.context_snapshot_label = label
        self.chat_layout.addWidget(label, alignment=ALIGN_LEFT)

    def add_debug_message(self, message: str) -> None:
        """Pridá debug/info blok (napr. celý prompt/odpoveď LLM)."""
        label = QLabel(message)
        label.setWordWrap(True)
        label.setTextInteractionFlags(TEXT_SELECTABLE_BY_MOUSE)
        label.setStyleSheet(
            "color: #9ac7ff; background: #0d1620; border: 1px solid #3a4c63; "
            "border-radius: 6px; padding: 6px 10px; font-family: 'Fira Code', 'Consolas'; "
            "font-size: 11px;"
        )
        self.chat_layout.addWidget(label, alignment=ALIGN_LEFT)
        self._scroll_to_bottom()

    def add_profiling_info(self, title: str, data: dict[str, str]) -> None:
        """Pridá štruktúrovaný profiling blok ako chat bublinu."""
        self.add_agent_activity(f"📊 {title}", section="planning")
        for key, value in data.items():
            self.add_agent_activity(f"{key}: {value}", section="planning")

    @staticmethod
    def _tool_raw_enabled() -> bool:
        raw = (os.getenv("SHOW_AGENT_TOOL_RAW", "") or "").strip().lower()
        return raw in {"1", "true", "yes", "on"}

    @staticmethod
    def _short_text(value: object, max_len: int = 80) -> str:
        text = str(value).replace("\n", " ").strip()
        if len(text) <= max_len:
            return text
        return text[:max_len] + "..."

    @staticmethod
    def _normalize_tool_name(tool_name: str) -> str:
        normalized = (tool_name or "").strip().lower()
        for separator in ("/", ".", "::", ":", "__"):
            if separator in normalized:
                normalized = normalized.split(separator)[-1]
        return normalized.replace("-", "_").strip()

    @staticmethod
    def _model_prefix(model_name: str | None) -> str:
        if not model_name:
            return ""
        cleaned = model_name.strip()
        if not cleaned:
            return ""
        short = cleaned if len(cleaned) <= 24 else cleaned[:24] + "..."
        return f"[{short}] "

    @staticmethod
    def _placements_summary(placements: object) -> str:
        if not isinstance(placements, list) or not placements:
            return "bez písmen"

        letters: list[str] = []
        start: tuple[int, int] | None = None
        for item in placements[:7]:
            if not isinstance(item, dict):
                continue
            letter = item.get("letter")
            if isinstance(letter, str) and letter:
                letters.append(letter)
            row = item.get("row")
            col = item.get("col")
            if start is None and isinstance(row, int) and isinstance(col, int):
                start = (row, col)

        word_preview = "".join(letters) if letters else f"{len(placements)} písmen"
        if start is None:
            return word_preview
        return f"{word_preview} @ ({start[0]},{start[1]})"

    def _summarize_tool_args(self, tool_name: str, args: dict[str, Any] | str) -> str:
        if not isinstance(args, dict):
            return self._short_text(args, 120)

        parts: list[str] = []
        for key, value in args.items():
            if key in {"board_grid", "grid"}:
                if isinstance(value, list):
                    rows = len(value)
                    cols = len(value[0]) if value and isinstance(value[0], str) else "?"
                    parts.append(f"{key}={rows}x{cols}")
                else:
                    parts.append(f"{key}=doska")
                continue

            if key == "premium_grid":
                parts.append("premium_grid=layout")
                continue

            if key == "placements" and isinstance(value, list):
                letters: list[str] = []
                for item in value[:7]:
                    if isinstance(item, dict):
                        letter = item.get("letter")
                        if isinstance(letter, str) and letter:
                            letters.append(letter)
                letters_preview = "".join(letters)
                if letters_preview:
                    parts.append(f"placements={len(value)} ({letters_preview})")
                else:
                    parts.append(f"placements={len(value)}")
                continue

            if key in {"messages", "contents"} and isinstance(value, list):
                parts.append(f"{key}={len(value)}")
                continue

            if isinstance(value, list):
                parts.append(f"{key}={len(value)} položiek")
                continue

            if isinstance(value, dict):
                parts.append(f"{key}=obj")
                continue

            parts.append(f"{key}={self._short_text(value, 48)}")

        if not parts:
            return f"{tool_name}: bez argumentov"
        return ", ".join(parts[:5])

    def _summarize_tool_result(self, result: Any, is_error: bool = False) -> str:
        if isinstance(result, dict):
            if is_error or "error" in result:
                return self._short_text(result.get("error", "Neznáma chyba"), 140)

            if "valid" in result:
                state = "validné" if bool(result.get("valid")) else "neplatné"
                reason = result.get("reason", "")
                if reason:
                    return f"{state} ({self._short_text(reason, 100)})"
                return state

            if "total_score" in result:
                score = result.get("total_score", 0)
                words = result.get("words")
                word_count = len(words) if isinstance(words, list) else 0
                return f"score={score}, words={word_count}"

            if "words" in result and isinstance(result["words"], list):
                words_val = result["words"]
                if words_val and isinstance(words_val[0], dict):
                    words_only: list[str] = []
                    for item in words_val[:4]:
                        if isinstance(item, dict):
                            word = item.get("word")
                            if isinstance(word, str):
                                words_only.append(word)
                    if words_only:
                        suffix = "..." if len(words_val) > 4 else ""
                        return f"slová: {', '.join(words_only)}{suffix}"
                return f"slová: {len(words_val)}"

            if "premiums" in result and isinstance(result["premiums"], list):
                return f"premium squares: {len(result['premiums'])}"

            if "rack" in result:
                rack_val = result.get("rack", "")
                count_val = result.get("count")
                if isinstance(count_val, int):
                    return f"rack={rack_val} ({count_val})"
                return f"rack={rack_val}"

            keys = list(result.keys())
            return f"výstup: {', '.join(keys[:5])}"

        if isinstance(result, list):
            return f"{len(result)} položiek"

        return self._short_text(result, 140)

    @staticmethod
    def _source_label(source: str) -> str:
        src = source.strip().lower()
        mapping = {
            "fastdict": "lokálny slovník",
            "fastdict_english": "lokálny slovník",
            "juls_api": "online slovník",
            "tier1_negative_short": "lokálny slovník",
            "tier2_negative": "online slovník",
            "pattern_validation": "kontrola formátu",
        }
        return mapping.get(src, source)

    @staticmethod
    def _format_ms(value: object) -> str:
        if isinstance(value, (int, float)):
            return f"{value:.1f} ms"
        return ""

    def _build_tool_event_message(
        self,
        tool_name: str,
        args: dict[str, Any] | str,
        result: Any,
        is_error: bool = False,
        model_name: str | None = None,
    ) -> tuple[str, str | None, str]:
        normalized_tool = self._normalize_tool_name(tool_name)
        model_prefix = self._model_prefix(model_name)
        merge_key: str | None = None
        section = self._section_for_tool(normalized_tool)

        if is_error:
            err = self._summarize_tool_result(result, is_error=True)
            return f"{model_prefix}❌ {normalized_tool}: {err}", merge_key, section

        args_dict = args if isinstance(args, dict) else {}
        result_dict = result if isinstance(result, dict) else {}

        if normalized_tool in {"validate_word_slovak", "validate_word_english"}:
            word = "?"
            if isinstance(args_dict, dict):
                arg_word = args_dict.get("word")
                if isinstance(arg_word, str) and arg_word.strip():
                    word = arg_word.strip()

            valid = bool(result_dict.get("valid", False))
            merge_key = f"tool:{normalized_tool}:{model_name or '-'}"

            state = self._word_validation_state.setdefault(
                merge_key,
                {"total": 0, "valid": 0, "invalid": 0, "recent": []},
            )
            state["total"] += 1
            if valid:
                state["valid"] += 1
            else:
                state["invalid"] += 1
            mark = "✅" if valid else "❌"
            recent = state["recent"]
            if isinstance(recent, list):
                recent.append(f"{word}{mark}")
                if len(recent) > 4:
                    del recent[:-4]

            source_raw = result_dict.get("source")
            source = self._source_label(str(source_raw)) if source_raw else ""
            elapsed = self._format_ms(result_dict.get("time_ms"))
            tier = result_dict.get("tier")
            details: list[str] = []
            if isinstance(tier, int):
                details.append(f"tier {tier}")
            if source:
                details.append(source)
            if result_dict.get("cached"):
                details.append("cache")
            if elapsed:
                details.append(elapsed)
            recent_text = ", ".join(recent) if isinstance(recent, list) else ""
            details_text = f" | posledné overenie: {', '.join(details)}" if details else ""
            lang = "SK" if normalized_tool.endswith("slovak") else "EN"
            return (
                f"{model_prefix}📚 Slovník {lang}: {state['total']} kontrol "
                f"(✅ {state['valid']} / ❌ {state['invalid']}) | posledné: {recent_text}{details_text}",
                merge_key,
                "word_check",
            )

        if normalized_tool == "validate_move_legality":
            valid = bool(result_dict.get("valid", False))
            checks = result_dict.get("checks")
            ok_checks = 0
            all_checks = 0
            if isinstance(checks, dict):
                all_checks = len(checks)
                ok_checks = sum(1 for value in checks.values() if bool(value))
            reason = self._short_text(result_dict.get("reason", ""), 90)
            status = "OK" if valid else "neplatné"
            checks_text = f", kontroly {ok_checks}/{all_checks}" if all_checks else ""
            reason_text = f", {reason}" if reason else ""
            placement_text = self._placements_summary(args_dict.get("placements"))
            merge_key = f"tool:{normalized_tool}:{model_name or '-'}"
            return (
                f"{model_prefix}⚖️ Legalita ťahu ({placement_text}): {status}{checks_text}{reason_text}",
                merge_key,
                "word_check",
            )

        if normalized_tool in {"calculate_move_score", "scoring_score_words"}:
            score = result_dict.get("total_score", 0)
            placement_text = self._placements_summary(args_dict.get("placements"))
            words_value = result_dict.get("words")
            words_text = ""
            if isinstance(words_value, list) and words_value:
                scored_words: list[str] = []
                for item in words_value[:3]:
                    if isinstance(item, dict):
                        word_text = item.get("word")
                        if isinstance(word_text, str) and word_text:
                            scored_words.append(word_text)
                if scored_words:
                    suffix = "..." if len(words_value) > 3 else ""
                    words_text = f", slová: {', '.join(scored_words)}{suffix}"
            merge_key = f"tool:{normalized_tool}:{model_name or '-'}"
            return (
                f"{model_prefix}🧮 Skóre ({placement_text}): {score} bodov{words_text}",
                merge_key,
                "scoring",
            )

        if normalized_tool == "rules_extract_all_words":
            words_value = result_dict.get("words")
            extracted_words: list[str] = []
            if isinstance(words_value, list):
                for item in words_value[:4]:
                    if isinstance(item, dict):
                        word_text = item.get("word")
                        if isinstance(word_text, str) and word_text:
                            extracted_words.append(word_text)
            placement_text = self._placements_summary(args_dict.get("placements"))
            merge_key = f"tool:{normalized_tool}:{model_name or '-'}"
            if extracted_words:
                suffix = "..." if isinstance(words_value, list) and len(words_value) > 4 else ""
                return (
                    f"{model_prefix}🔤 Slová z ťahu ({placement_text}): {', '.join(extracted_words)}{suffix}",
                    merge_key,
                    "word_check",
                )
            return f"{model_prefix}🔤 Slová z ťahu ({placement_text}): žiadne", merge_key, "word_check"

        if normalized_tool == "get_rack_letters":
            rack = result_dict.get("rack", "")
            count = result_dict.get("count")
            if isinstance(count, int):
                return f"{model_prefix}🎒 Rack: {rack} ({count} písmen)", None, "planning"
            return f"{model_prefix}🎒 Rack: {rack}", None, "planning"

        if normalized_tool == "get_board_state":
            grid = result_dict.get("grid")
            if isinstance(grid, list):
                empty = 0
                for row in grid:
                    if isinstance(row, str):
                        empty += row.count(".")
                cells = len(grid) * (len(grid[0]) if grid and isinstance(grid[0], str) else 15)
                filled = max(0, cells - empty)
                return (
                    f"{model_prefix}🗺️ Stav dosky načítaný (obsadené polia: {filled})",
                    None,
                    "planning",
                )
            return f"{model_prefix}🗺️ Stav dosky načítaný", None, "planning"

        args_summary = self._summarize_tool_args(tool_name, args)
        res_summary = self._summarize_tool_result(result, is_error=False)
        return (
            f"{model_prefix}🛠️ {normalized_tool}: {args_summary} -> {res_summary}",
            merge_key,
            section,
        )

    def add_tool_call(
        self,
        tool_name: str,
        args: dict[str, Any] | str,
        *,
        model_name: str | None = None,
    ) -> None:
        """Zobrazí volanie interného nástroja."""
        normalized_tool = self._normalize_tool_name(tool_name)
        if not self._tool_raw_enabled():
            self._pending_tool_calls.append((normalized_tool, args, model_name))
            return

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
        model_prefix = self._model_prefix(model_name)
        name_label = QLabel(f"Calling: {model_prefix}{normalized_tool}")
        name_label.setStyleSheet("color: #ffb74d; font-weight: bold; font-family: 'Fira Code', monospace; font-size: 11px;")
        
        header_layout.addWidget(icon)
        header_layout.addWidget(name_label, stretch=1)
        layout.addLayout(header_layout)
        
        # Args display - verbose JSON
        import json
        arg_str = json.dumps(args, ensure_ascii=False, indent=2) if isinstance(args, dict) else str(args)
        arg_label = QLabel(arg_str)
        # Preserve newlines for JSON pretty print
        arg_label.setTextFormat(PLAIN_TEXT)
        arg_label.setStyleSheet("color: #d7e4d8; font-family: 'Fira Code', monospace; font-size: 10px; padding-left: 24px;")
        layout.addWidget(arg_label)
        
        self.chat_layout.addWidget(container, alignment=ALIGN_LEFT)
        self._scroll_to_bottom()

    def add_tool_result(
        self,
        tool_name: str,
        result: Any,
        is_error: bool = False,
        *,
        model_name: str | None = None,
    ) -> None:
        """Zobrazí výsledok volania nástroja."""
        normalized_tool = self._normalize_tool_name(tool_name)
        if not self._tool_raw_enabled():
            call_args: dict[str, Any] | str = {}
            has_call_args = False
            for idx, (pending_name, pending_args, pending_model_name) in enumerate(self._pending_tool_calls):
                if pending_name != normalized_tool:
                    continue
                if model_name and pending_model_name and pending_model_name != model_name:
                    continue
                call_args = pending_args
                has_call_args = True
                del self._pending_tool_calls[idx]
                break
            if not has_call_args:
                for idx, (pending_name, pending_args, _pending_model_name) in enumerate(self._pending_tool_calls):
                    if pending_name != normalized_tool:
                        continue
                    call_args = pending_args
                    has_call_args = True
                    del self._pending_tool_calls[idx]
                    break
            message, merge_key, section = self._build_tool_event_message(
                tool_name=tool_name,
                args=call_args,
                result=result,
                is_error=is_error,
                model_name=model_name,
            )
            self.add_agent_activity(message, merge_key=merge_key, section=section)
            return

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
        model_prefix = self._model_prefix(model_name)
        title = QLabel(f"{model_prefix}{normalized_tool} -> {'Error' if is_error else 'Result'}")
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
        res_label.setTextFormat(PLAIN_TEXT)
        res_label.setTextInteractionFlags(TEXT_SELECTABLE_BY_MOUSE)
        res_label.setStyleSheet("color: #d7e4d8; font-family: 'Fira Code', monospace; font-size: 10px; padding-left: 24px;")
        layout.addWidget(res_label)
        
        self.chat_layout.addWidget(container, alignment=ALIGN_LEFT)
        self._scroll_to_bottom()

    def add_agent_activity(
        self,
        message: str,
        *,
        merge_key: str | None = None,
        section: str | None = None,
    ) -> None:
        """Pridá informačnú správu o aktivite agenta do sekčného feedu."""
        normalized = self._normalize_section(section)
        if normalized is None:
            normalized = self._infer_activity_section(message, merge_key)
        if normalized not in self._SECTION_META:
            normalized = "planning"

        if not self._turn_sections_ready:
            self._start_new_turn_sections()

        card = self._ensure_section_card(normalized)
        entry_key = merge_key or ""
        entry_label, merged = card.append_entry(
            message,
            merge_key=entry_key if entry_key else None,
        )
        self.last_message_bubble = None
        entry_label.setStyleSheet(
            "color: #ebf7ed; font-size: 12px; line-height: 1.35; "
            "font-family: 'Fira Sans', 'Segoe UI', sans-serif;"
        )

        history_lookup = (normalized, entry_key)
        if entry_key and merged and history_lookup in self._section_history_indices:
            idx = self._section_history_indices[history_lookup]
            if 0 <= idx < len(self.chat_history):
                self.chat_history[idx] = f"[{normalized}] {message}"
        else:
            self.chat_history.append(f"[{normalized}] {message}")
            if entry_key:
                self._section_history_indices[history_lookup] = len(self.chat_history) - 1

        self._reset_activity_merge_state()
        self._render_context_info()
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
            self.chat_layout.addWidget(self.loading_label, alignment=ALIGN_LEFT)
        
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
        self.chat_layout.addWidget(bubble, alignment=ALIGN_LEFT)
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
        
        self.chat_layout.addWidget(bubble, alignment=ALIGN_LEFT)
        self.reasoning_bubble = bubble
        self.reasoning_label = bubble.set_plain_text("⏳ ")
        self.reasoning_label.setTextFormat(PLAIN_TEXT) # Ensure whitespace preserved
        
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
    
    def showEvent(self, event: QShowEvent) -> None:
        """Auto-focus input field when shown."""
        super().showEvent(event)
        self.input_field.setFocus()
