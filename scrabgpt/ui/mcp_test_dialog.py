"""MCP Test Dialog - UI pre testovanie MCP serverov a nástrojov."""

from __future__ import annotations

import asyncio
import html
import inspect
import json
import logging
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, cast

from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QFont, QTextCursor, QMouseEvent
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QTabWidget, 
    QWidget, QTextEdit, QComboBox, QLineEdit, QFormLayout, QGroupBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QSplitter, QFrame,
    QMessageBox, QFileDialog, QCheckBox, QSpinBox, QScrollArea, QInputDialog
)

from openai.types.chat import ChatCompletionMessageParam

from ..ai.mcp_tools import get_all_tool_names, get_tool_function
from ..ai.client import OpenAIClient

log = logging.getLogger("scrabgpt.ui.mcp_test")


class ClickableLabel(QLabel):
    """Label that emits clicked signal when clicked."""
    
    clicked = Signal()
    
    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Handle mouse press event."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class ClickableChatDisplay(QTextEdit):
    """QTextEdit with clickable message support for showing thinking."""
    
    message_clicked = Signal(str)  # Emits message_id when clicked
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._message_thinking_map: dict[str, str] = {}
        self._message_positions: dict[str, tuple[int, int]] = {}  # msg_id -> (start, end)
        self.setMouseTracking(True)
        self._last_hover_msg_id: str | None = None
    
    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Handle mouse clicks on messages."""
        if event.button() == Qt.MouseButton.LeftButton:
            cursor = self.cursorForPosition(event.pos())
            position = cursor.position()
            
            # Find which message was clicked
            for msg_id, (start, end) in self._message_positions.items():
                if start <= position <= end:
                    if msg_id in self._message_thinking_map:
                        self.message_clicked.emit(msg_id)
                        break
        
        super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """Update cursor when hovering over clickable messages."""
        cursor = self.cursorForPosition(event.pos())
        position = cursor.position()
        
        # Check if hovering over a clickable message
        hover_msg_id = None
        for msg_id, (start, end) in self._message_positions.items():
            if start <= position <= end and msg_id in self._message_thinking_map:
                hover_msg_id = msg_id
                break
        
        if hover_msg_id != self._last_hover_msg_id:
            if hover_msg_id:
                self.viewport().setCursor(Qt.CursorShape.PointingHandCursor)
            else:
                self.viewport().setCursor(Qt.CursorShape.ArrowCursor)
            self._last_hover_msg_id = hover_msg_id
        
        super().mouseMoveEvent(event)


class MCPConnectionWorker(QThread):
    """Worker thread pre MCP pripojenia."""
    
    connection_result = Signal(dict)  # {server_name: str, success: bool, tools: list, error: str}
    log_message = Signal(str)  # Log správy
    
    def __init__(self, server_config: dict, server_name: str):
        super().__init__()
        self.server_config = server_config
        self.server_name = server_name
        self._stop_requested = False
    
    def run(self):
        """Spusti MCP pripojenie v worker threade."""
        try:
            self.log_message.emit(f"🔌 Pripájam sa k MCP serveru: {self.server_name}")
            
            # Simulácia MCP pripojenia - v skutočnosti by tu bol mcp-use kód
            # Pre teraz len testujeme lokálne nástroje
            if self.server_name == "scrabble":
                # Načítaj lokálne nástroje
                tools = []
                for tool_name in get_all_tool_names():
                    tool_func = get_tool_function(tool_name)
                    tools.append({
                        "name": tool_name,
                        "description": tool_func.__doc__ or "Bez popisu",
                        "parameters": self._extract_parameters(tool_func)
                    })
                
                self.log_message.emit(f"✅ Načítaných {len(tools)} nástrojov z lokálneho servera")
                self.connection_result.emit({
                    "server_name": self.server_name,
                    "success": True,
                    "tools": tools,
                    "error": None
                })
            else:
                # Simulácia externého servera
                self.log_message.emit(f"⚠️ Simulácia externého servera: {self.server_name}")
                self.connection_result.emit({
                    "server_name": self.server_name,
                    "success": True,
                    "tools": [
                        {
                            "name": "test_tool",
                            "description": "Testovací nástroj",
                            "parameters": {"param1": "string", "param2": "number"}
                        }
                    ],
                    "error": None
                })
                
        except Exception as e:
            self.log_message.emit(f"❌ Chyba pripojenia: {e}")
            self.connection_result.emit({
                "server_name": self.server_name,
                "success": False,
                "tools": [],
                "error": str(e)
            })
    
    def _extract_parameters(self, tool_func) -> dict:
        """Extrahuj parametre z tool funkcie."""
        import inspect
        sig = inspect.signature(tool_func)
        params = {}
        for name, param in sig.parameters.items():
            if name == 'self':
                continue
            param_type = "string"
            if param.annotation != inspect.Parameter.empty:
                if param.annotation == bool:
                    param_type = "boolean"
                elif param.annotation == int:
                    param_type = "number"
                elif param.annotation == list:
                    param_type = "array"
            params[name] = param_type
        return params
    
    def stop(self):
        """Zastav worker."""
        self._stop_requested = True


class MCPToolTestWorker(QThread):
    """Worker thread pre testovanie MCP nástrojov."""
    
    test_result = Signal(dict)  # {tool_name: str, success: bool, result: any, error: str}
    log_message = Signal(str)  # Log správy
    
    def __init__(self, tool_name: str, parameters: dict, server_name: str):
        super().__init__()
        self.tool_name = tool_name
        self.parameters = parameters
        self.server_name = server_name
        self._stop_requested = False
    
    def run(self):
        """Spusti test nástroja v worker threade."""
        try:
            self.log_message.emit(f"🔧 Testujem nástroj: {self.tool_name}")
            self.log_message.emit(f"📝 Parametre: {json.dumps(self.parameters, indent=2)}")
            
            if self.server_name == "scrabble":
                # Test lokálneho nástroja
                tool_func = get_tool_function(self.tool_name)
                result = tool_func(**self.parameters)
                
                self.log_message.emit(f"✅ Nástroj úspešne vykonaný")
                self.test_result.emit({
                    "tool_name": self.tool_name,
                    "success": True,
                    "result": result,
                    "error": None
                })
            else:
                # Simulácia externého nástroja
                self.log_message.emit(f"⚠️ Simulácia externého nástroja")
                result = {"status": "simulated", "message": "Toto je simulovaný výsledok"}
                
                self.test_result.emit({
                    "tool_name": self.tool_name,
                    "success": True,
                    "result": result,
                    "error": None
                })
                
        except Exception as e:
            self.log_message.emit(f"❌ Chyba testu: {e}")
            self.test_result.emit({
                "tool_name": self.tool_name,
                "success": False,
                "result": None,
                "error": str(e)
            })


class AgentChatWorker(QThread):
    """Worker pre agent chat s tool calling podporou."""
    
    message_received = Signal(str, dict)  # (content, full_message)
    tool_call_started = Signal(str, dict)  # (tool_name, arguments)
    tool_call_finished = Signal(str, dict)  # (tool_name, result)
    error_occurred = Signal(str)
    status_update = Signal(str)
    
    def __init__(
        self, 
        client: OpenAIClient,
        messages: list,
        available_functions: list[dict],
        auto_execute: bool = True
    ):
        super().__init__()
        self.client = client
        self.messages = messages
        self.available_functions = available_functions
        self.auto_execute = auto_execute
        self._stop_requested = False
    
    def run(self):
        """Run agent loop with tool calling."""
        try:
            max_iterations = 10  # Prevent infinite loops
            iteration = 0
            
            while iteration < max_iterations and not self._stop_requested:
                iteration += 1
                
                # Call LLM with tools
                self.status_update.emit("Volám LLM...")
                
                response = self.client.client.chat.completions.create(
                    model=self.client.model,
                    messages=self.messages,
                    tools=[{"type": "function", "function": f} for f in self.available_functions],
                    tool_choice="auto",
                    max_completion_tokens=self.client.ai_move_max_output_tokens
                )
                
                message = response.choices[0].message
                
                # Extract thinking/reasoning if present
                full_message = {
                    "role": "assistant",
                    "content": message.content or ""
                }
                
                if hasattr(message, 'thinking') and message.thinking:
                    full_message["thinking"] = message.thinking
                elif hasattr(message, 'reasoning') and message.reasoning:
                    full_message["reasoning"] = message.reasoning
                
                # Check for tool calls
                if message.tool_calls:
                    full_message["tool_calls"] = []
                    
                    for tool_call in message.tool_calls:
                        tool_name = tool_call.function.name
                        tool_args = json.loads(tool_call.function.arguments)
                        tool_id = tool_call.id
                        
                        full_message["tool_calls"].append({
                            "id": tool_id,
                            "type": "function",
                            "function": {
                                "name": tool_name,
                                "arguments": tool_call.function.arguments
                            }
                        })
                        
                        # Emit tool call signal
                        self.tool_call_started.emit(tool_name, tool_args)
                        
                        # Execute tool if auto-execute is enabled
                        if self.auto_execute:
                            self.status_update.emit(f"Vykonávam {tool_name}...")
                            
                            try:
                                tool_func = get_tool_function(tool_name)
                                result = tool_func(**tool_args)
                                
                                # Emit tool result
                                self.tool_call_finished.emit(tool_name, {
                                    "status": "success",
                                    "result": result
                                })
                                
                                # Add tool result to messages
                                self.messages.append({
                                    "role": "tool",
                                    "tool_call_id": tool_id,
                                    "content": json.dumps(result)
                                })
                                
                            except Exception as e:
                                error_msg = str(e)
                                self.tool_call_finished.emit(tool_name, {
                                    "status": "error",
                                    "error": error_msg
                                })
                                
                                self.messages.append({
                                    "role": "tool",
                                    "tool_call_id": tool_id,
                                    "content": json.dumps({"error": error_msg})
                                })
                    
                    # Add assistant message with tool calls to history
                    self.messages.append(full_message)
                    
                    # Continue loop to get final answer after tools
                    continue
                    
                else:
                    # No more tool calls - final answer
                    self.messages.append(full_message)
                    self.message_received.emit(
                        full_message.get("content", ""),
                        full_message
                    )
                    break
                    
        except Exception as e:
            log.exception("Agent chat failed")
            self.error_occurred.emit(str(e))
    
    def stop(self):
        """Zastav worker."""
        self._stop_requested = True


# Helper functions for tool conversion

def _mcp_tool_to_openai_function(tool_name: str) -> dict:
    """Convert MCP tool to OpenAI function schema."""
    tool_func = get_tool_function(tool_name)
    
    # Extract signature
    sig = inspect.signature(tool_func)
    
    parameters = {
        "type": "object",
        "properties": {},
        "required": []
    }
    
    for name, param in sig.parameters.items():
        if name == 'self':
            continue
            
        param_schema = {"type": "string"}  # default
        if param.annotation != inspect.Parameter.empty:
            if param.annotation == bool:
                param_schema = {"type": "boolean"}
            elif param.annotation == int:
                param_schema = {"type": "integer"}
            elif param.annotation == list:
                param_schema = {"type": "array", "items": {"type": "string"}}
            elif param.annotation == dict:
                param_schema = {"type": "object"}
        
        # Extract description from docstring (basic)
        doc = tool_func.__doc__ or ""
        param_desc = f"Parameter {name}"
        
        param_schema["description"] = param_desc
        parameters["properties"][name] = param_schema
        
        if param.default == inspect.Parameter.empty:
            parameters["required"].append(name)
    
    return {
        "name": tool_name,
        "description": tool_func.__doc__ or f"MCP tool: {tool_name}",
        "parameters": parameters
    }


def _get_available_functions() -> list[dict]:
    """Get all MCP tools as OpenAI functions."""
    functions = []
    for tool_name in get_all_tool_names():
        try:
            func_def = _mcp_tool_to_openai_function(tool_name)
            functions.append(func_def)
        except Exception as e:
            log.warning(f"Failed to convert tool {tool_name}: {e}")
    return functions


class MCPTestDialog(QDialog):
    """Hlavné okno pre testovanie MCP serverov a nástrojov."""
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        
        self.setWindowTitle("🔧 MCP Testovacie Rozhranie")
        self.setModal(False)  # Non-modal
        self.resize(1200, 800)
        
        # State
        self.connected_servers: Dict[str, List[dict]] = {}  # server_name -> tools
        self.workers: Dict[str, QThread] = {}  # worker_name -> worker
        self.saved_servers: Dict[str, dict] = {}  # server_name -> config
        self.logs_dialog: Optional[QDialog] = None
        
        # Chat state
        self.chat_client: Optional[OpenAIClient] = None
        self.chat_messages: list = []
        self.chat_available_functions: list[dict] = []
        self.chat_workers: list[AgentChatWorker] = []
        self.chat_request_counter = 0  # Track request/response pairs
        
        # Animation state
        self.loading_timer: Optional[QTimer] = None
        self.loading_dots = 0
        self.loading_cursor_position = -1
        self.thinking_timer: Optional[QTimer] = None
        self.thinking_text = ""
        self.thinking_position = 0
        self.thinking_speed = 8  # characters per tick
        
        # UI setup
        self._setup_ui()
        self._load_default_servers()
    
    def _setup_ui(self):
        """Nastav UI komponenty."""
        # Eye candy on-hover reacting dark forest theme
        self.setStyleSheet("""
            QDialog {
                background-color: #0f1a12;
                color: #e8f5e9;
            }
            QLabel {
                color: #e8f5e9;
            }
            QTabWidget::pane {
                border: 1px solid #2f5c39;
                background: #0f1a12;
            }
            QTabBar::tab {
                background: #1a2f1f;
                color: #b6e0bd;
                padding: 8px 16px;
                border: 1px solid #2f5c39;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background: #295c33;
                color: #e8f5e9;
                font-weight: bold;
                border-bottom: 2px solid #4caf50;
            }
            QTabBar::tab:hover {
                background: #213f29;
                border-color: #4caf50;
            }
            QPushButton {
                background: #1a2f1f;
                color: #e8f5e9;
                border: 1px solid #2f5c39;
                border-radius: 4px;
                padding: 6px 12px;
                font-size: 12px;
            }
            QPushButton:hover {
                background: #213f29;
                border-color: #4caf50;
            }
            QPushButton:pressed {
                background: #152820;
            }
            QPushButton:disabled {
                background: #0a0a0a;
                color: #666;
                border-color: #333;
            }
            QComboBox {
                background: #000000;
                color: #e8f5e9;
                border: 1px solid #2f5c39;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 12px;
            }
            QComboBox:hover {
                border-color: #4caf50;
                background: #0a0a0a;
            }
            QComboBox:focus {
                border-color: #4caf50;
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
            QComboBox QAbstractItemView {
                background: #000000;
                color: #e8f5e9;
                selection-background-color: #295c33;
                border: 1px solid #2f5c39;
            }
            QLineEdit {
                background: #000000;
                color: #e8f5e9;
                border: 1px solid #2f5c39;
                border-radius: 4px;
                padding: 6px 8px;
                font-size: 12px;
            }
            QLineEdit:hover {
                border-color: #4caf50;
            }
            QLineEdit:focus {
                border-color: #4caf50;
                background: #0a0a0a;
            }
            QTextEdit {
                background: #000000;
                color: #e8f5e9;
                border: 1px solid #2f5c39;
                border-radius: 4px;
                padding: 8px;
                font-family: 'Monospace', 'Courier New';
                font-size: 11px;
            }
            QTextEdit:hover {
                border-color: #4caf50;
            }
            QTextEdit:focus {
                border-color: #4caf50;
                background: #0a0a0a;
            }
            QTableWidget {
                background: #000000;
                color: #e8f5e9;
                border: 1px solid #2f5c39;
                gridline-color: #2f5c39;
                selection-background-color: #295c33;
            }
            QTableWidget::item {
                padding: 4px 8px;
            }
            QTableWidget::item:hover {
                background: #1a2f1f;
            }
            QHeaderView::section {
                background: #1a2f1f;
                color: #e8f5e9;
                border: 1px solid #2f5c39;
                padding: 4px 8px;
                font-weight: bold;
            }
            QHeaderView::section:hover {
                background: #213f29;
            }
            QGroupBox {
                color: #b6e0bd;
                font-weight: bold;
                border: 1px solid #2f5c39;
                border-radius: 4px;
                margin-top: 8px;
                padding-top: 8px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 8px;
                padding: 0 4px 0 4px;
            }
            QCheckBox {
                color: #e8f5e9;
            }
            QCheckBox:hover {
                color: #4caf50;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)
        
        # Pseudo toolbar pre MCP server management
        self._create_pseudo_toolbar(layout)
        
        # Tab widget
        self.tabs = QTabWidget()
        
        # Server Management tab
        server_tab = self._create_server_tab()
        self.tabs.addTab(server_tab, "🔌 Správa Serverov")
        
        # Tool Testing tab
        tool_tab = self._create_tool_tab()
        self.tabs.addTab(tool_tab, "🔧 Testovanie Nástrojov")
        
        # Agent Chat tab
        chat_tab = self._create_chat_tab()
        self.tabs.addTab(chat_tab, "💬 Agent Chat")
        
        layout.addWidget(self.tabs)
        
        # Status bar (clickable)
        self.status_label = ClickableLabel("Pripravené")
        self.status_label.clicked.connect(self._open_logs_dialog)
        self.status_label.setStyleSheet(
            "color: #4caf50; font-size: 12px; font-weight: bold; "
            "padding: 4px 8px; background: #000000; "
            "border-top: 1px solid #2f5c39;"
        )
        self.status_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.status_label.setToolTip("Kliknite pre otvorenie logov")
        layout.addWidget(self.status_label)
    
    def _create_pseudo_toolbar(self, parent_layout: QVBoxLayout):
        """Vytvor pseudo toolbar pre MCP server management."""
        toolbar_frame = QFrame()
        toolbar_frame.setStyleSheet(
            "QFrame { "
            "background: #000000; "
            "border: 1px solid #2f5c39; "
            "border-radius: 6px; "
            "padding: 8px; "
            "}"
        )
        
        toolbar_layout = QHBoxLayout(toolbar_frame)
        toolbar_layout.setSpacing(8)
        
        # Server dropdown
        server_label = QLabel("MCP Server:")
        server_label.setStyleSheet("color: #b6e0bd; font-weight: bold; font-size: 13px;")
        toolbar_layout.addWidget(server_label)
        
        self.server_dropdown = QComboBox()
        self.server_dropdown.setMinimumWidth(200)
        self.server_dropdown.currentTextChanged.connect(self._on_server_selected)
        toolbar_layout.addWidget(self.server_dropdown)
        
        # Buttons
        self.add_server_btn = QPushButton("➕ Pridať MCP server")
        self.add_server_btn.clicked.connect(self._show_add_server_dialog)
        self.add_server_btn.setStyleSheet(self._get_toolbar_button_style())
        toolbar_layout.addWidget(self.add_server_btn)
        
        self.delete_server_btn = QPushButton("🗑️ Zmazať")
        self.delete_server_btn.clicked.connect(self._delete_server)
        self.delete_server_btn.setEnabled(False)
        self.delete_server_btn.setStyleSheet(self._get_toolbar_button_style())
        toolbar_layout.addWidget(self.delete_server_btn)
        
        self.rename_server_btn = QPushButton("✎ Premenovať")
        self.rename_server_btn.clicked.connect(self._rename_server)
        self.rename_server_btn.setEnabled(False)
        self.rename_server_btn.setStyleSheet(self._get_toolbar_button_style())
        toolbar_layout.addWidget(self.rename_server_btn)
        
        toolbar_layout.addStretch()
        parent_layout.addWidget(toolbar_frame)
    
    def _get_toolbar_button_style(self) -> str:
        """Vráť štýl pre toolbar tlačidlá."""
        return """
            QPushButton {
                background: #1a2f1f;
                color: #e8f5e9;
                border: 1px solid #2f5c39;
                border-radius: 4px;
                padding: 6px 12px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #213f29;
                border-color: #4caf50;
            }
            QPushButton:pressed {
                background: #152820;
            }
            QPushButton:disabled {
                background: #0a0a0a;
                color: #666;
                border-color: #333;
            }
        """
    
    def _create_server_tab(self) -> QWidget:
        """Vytvor tab pre správu serverov."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)
        
        # Server configuration section (zobrazí sa len ak je server vybraný)
        self.config_group = QGroupBox("Konfigurácia Servera")
        self.config_group.setVisible(False)
        config_layout = QFormLayout(self.config_group)
        
        # Server name
        self.server_name_edit = QLineEdit()
        self.server_name_edit.setPlaceholderText("Názov servera (napr. scrabble)")
        config_layout.addRow("Názov servera:", self.server_name_edit)
        
        # Connection type
        self.connection_type_combo = QComboBox()
        self.connection_type_combo.addItems(["Príkaz (Command)", "URL + Port"])
        self.connection_type_combo.currentTextChanged.connect(self._on_connection_type_changed)
        config_layout.addRow("Typ pripojenia:", self.connection_type_combo)
        
        # Command fields (default visible)
        self.command_label = QLabel("Príkaz:")
        self.command_edit = QLineEdit()
        self.command_edit.setPlaceholderText("Príkaz (napr. poetry)")
        config_layout.addRow(self.command_label, self.command_edit)
        
        self.args_label = QLabel("Argumenty:")
        self.args_edit = QLineEdit()
        self.args_edit.setPlaceholderText("Argumenty oddelené čiarkou")
        config_layout.addRow(self.args_label, self.args_edit)
        
        # URL fields (hidden by default)
        self.url_label = QLabel("URL:")
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("URL (napr. localhost)")
        self.url_label.setVisible(False)
        self.url_edit.setVisible(False)
        config_layout.addRow(self.url_label, self.url_edit)
        
        self.port_label = QLabel("Port:")
        self.port_edit = QLineEdit()
        self.port_edit.setPlaceholderText("Port (napr. 8080)")
        self.port_label.setVisible(False)
        self.port_edit.setVisible(False)
        config_layout.addRow(self.port_label, self.port_edit)
        
        # Description
        self.description_edit = QLineEdit()
        self.description_edit.setPlaceholderText("Popis servera")
        config_layout.addRow("Popis:", self.description_edit)
        
        layout.addWidget(self.config_group)
        
        # Connection buttons
        button_layout = QHBoxLayout()
        
        self.connect_btn = QPushButton("🔌 Pripojiť")
        self.connect_btn.clicked.connect(self._connect_server)
        self.connect_btn.setEnabled(False)
        button_layout.addWidget(self.connect_btn)
        
        self.disconnect_btn = QPushButton("🔌 Odpojiť")
        self.disconnect_btn.clicked.connect(self._disconnect_server)
        self.disconnect_btn.setEnabled(False)
        button_layout.addWidget(self.disconnect_btn)
        
        button_layout.addStretch()
        layout.addLayout(button_layout)
        
        # Connected servers table
        servers_group = QGroupBox("Pripojené Servery")
        servers_layout = QVBoxLayout(servers_group)
        
        self.servers_table = QTableWidget()
        self.servers_table.setColumnCount(4)
        self.servers_table.setHorizontalHeaderLabels(["Server", "Status", "Nástroje", "Akcie"])
        self.servers_table.horizontalHeader().setStretchLastSection(True)
        self.servers_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        servers_layout.addWidget(self.servers_table)
        
        layout.addWidget(servers_group)
        
        return widget
    
    def _create_tool_tab(self) -> QWidget:
        """Vytvor tab pre testovanie nástrojov."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)
        
        # Tool selection section
        selection_group = QGroupBox("Výber Nástroja")
        selection_layout = QFormLayout(selection_group)
        
        # Server selection
        self.tool_server_combo = QComboBox()
        self.tool_server_combo.currentTextChanged.connect(self._on_server_changed)
        selection_layout.addRow("Server:", self.tool_server_combo)
        
        # Tool selection
        self.tool_combo = QComboBox()
        self.tool_combo.currentTextChanged.connect(self._on_tool_changed)
        selection_layout.addRow("Nástroj:", self.tool_combo)
        
        layout.addWidget(selection_group)
        
        # Parameters section
        params_group = QGroupBox("Parametre")
        params_layout = QVBoxLayout(params_group)
        
        # Parameters table
        self.params_table = QTableWidget()
        self.params_table.setColumnCount(3)
        self.params_table.setHorizontalHeaderLabels(["Parameter", "Typ", "Hodnota"])
        self.params_table.horizontalHeader().setStretchLastSection(True)
        params_layout.addWidget(self.params_table)
        
        # Parameter buttons
        param_button_layout = QHBoxLayout()
        
        self.add_param_btn = QPushButton("➕ Pridať parameter")
        self.add_param_btn.clicked.connect(self._add_parameter)
        param_button_layout.addWidget(self.add_param_btn)
        
        self.remove_param_btn = QPushButton("➖ Odstrániť parameter")
        self.remove_param_btn.clicked.connect(self._remove_parameter)
        param_button_layout.addWidget(self.remove_param_btn)
        
        param_button_layout.addStretch()
        params_layout.addLayout(param_button_layout)
        
        layout.addWidget(params_group)
        
        # Test execution section
        test_group = QGroupBox("Testovanie")
        test_layout = QVBoxLayout(test_group)
        
        # Test button
        self.test_btn = QPushButton("🚀 Spustiť test")
        self.test_btn.clicked.connect(self._run_tool_test)
        self.test_btn.setEnabled(False)
        test_layout.addWidget(self.test_btn)
        
        # Results
        self.results_text = QTextEdit()
        self.results_text.setMaximumHeight(200)
        self.results_text.setPlaceholderText("Výsledky testu sa zobrazia tu...")
        test_layout.addWidget(self.results_text)
        
        layout.addWidget(test_group)
        
        return widget
    
    
    def _load_default_servers(self):
        """Načítaj predvolené servery."""
        # Načítaj scrabble_mcp.json ak existuje
        config_path = Path("scrabble_mcp.json")
        if config_path.exists():
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                
                for server_name, server_config in config.get("mcpServers", {}).items():
                    # Pridaj do saved_servers
                    self.saved_servers[server_name] = {
                        "type": "command",
                        "command": server_config.get("command", ""),
                        "args": server_config.get("args", []),
                        "description": server_config.get("description", "")
                    }
                    
                self._update_server_dropdown()
                self._log_message("📁 Načítaná konfigurácia z scrabble_mcp.json")
            except Exception as e:
                self._log_message(f"❌ Chyba načítania konfigurácie: {e}")
    
    def _connect_server(self):
        """Pripoj MCP server."""
        server_name = self.server_dropdown.currentText()
        if not server_name or server_name not in self.saved_servers:
            QMessageBox.warning(self, "Chyba", "Vyberte server z dropdown")
            return
        
        if server_name in self.connected_servers:
            QMessageBox.warning(self, "Chyba", f"Server '{server_name}' je už pripojený")
            return
        
        # Získaj konfiguráciu servera
        server_config = self.saved_servers[server_name]
        
        # Spusti worker pre pripojenie
        worker = MCPConnectionWorker(server_config, server_name)
        worker.connection_result.connect(self._on_connection_result)
        worker.log_message.connect(self._log_message)
        
        self.workers[f"connect_{server_name}"] = worker
        worker.start()
        
        self.connect_btn.setEnabled(False)
        self.status_label.setText(f"Pripájam sa k {server_name}...")
    
    def _disconnect_server(self):
        """Odpoj MCP server."""
        server_name = self.server_dropdown.currentText()
        if not server_name:
            return
        
        if server_name in self.connected_servers:
            del self.connected_servers[server_name]
            self._update_servers_table()
            self._update_tool_server_combo()
            self._log_message(f"🔌 Server '{server_name}' odpojený")
            self.status_label.setText(f"Server '{server_name}' odpojený")
    
    
    def _on_connection_result(self, result: dict):
        """Spracuj výsledok pripojenia."""
        server_name = result["server_name"]
        success = result["success"]
        tools = result["tools"]
        error = result["error"]
        
        if success:
            self.connected_servers[server_name] = tools
            self._update_servers_table()
            self._update_tool_server_combo()
            self._log_message(f"✅ Server '{server_name}' úspešne pripojený ({len(tools)} nástrojov)")
            self.status_label.setText(f"Server '{server_name}' pripojený")
        else:
            self._log_message(f"❌ Chyba pripojenia k '{server_name}': {error}")
            self.status_label.setText(f"Chyba pripojenia k '{server_name}'")
        
        self.connect_btn.setEnabled(True)
        
        # Vyčisti worker
        worker_key = f"connect_{server_name}"
        if worker_key in self.workers:
            del self.workers[worker_key]
    
    def _update_servers_table(self):
        """Aktualizuj tabuľku serverov."""
        self.servers_table.setRowCount(len(self.connected_servers))
        
        for row, (server_name, tools) in enumerate(self.connected_servers.items()):
            self.servers_table.setItem(row, 0, QTableWidgetItem(server_name))
            self.servers_table.setItem(row, 1, QTableWidgetItem("🟢 Pripojený"))
            self.servers_table.setItem(row, 2, QTableWidgetItem(str(len(tools))))
            
            # Disconnect button
            disconnect_btn = QPushButton("🔌 Odpojiť")
            disconnect_btn.clicked.connect(lambda checked, s=server_name: self._disconnect_server_by_name(s))
            self.servers_table.setCellWidget(row, 3, disconnect_btn)
    
    def _disconnect_server_by_name(self, server_name: str):
        """Odpoj server podľa názvu."""
        if server_name in self.connected_servers:
            del self.connected_servers[server_name]
            self._update_servers_table()
            self._update_tool_server_combo()
            self._log_message(f"🔌 Server '{server_name}' odpojený")
            self.status_label.setText(f"Server '{server_name}' odpojený")
    
    def _update_tool_server_combo(self):
        """Aktualizuj combo box serverov pre testovanie nástrojov."""
        self.tool_server_combo.clear()
        for server_name in self.connected_servers.keys():
            self.tool_server_combo.addItem(server_name)
    
    def _on_server_changed(self, server_name: str):
        """Spracuj zmenu servera v tool tab."""
        self.tool_combo.clear()
        
        if server_name and server_name in self.connected_servers:
            tools = self.connected_servers[server_name]
            for tool in tools:
                self.tool_combo.addItem(tool["name"], tool)
    
    def _on_tool_changed(self, tool_name: str):
        """Spracuj zmenu nástroja."""
        if not tool_name:
            self.params_table.setRowCount(0)
            self.test_btn.setEnabled(False)
            return
        
        # Načítaj parametre nástroja
        tool_data = self.tool_combo.currentData()
        if tool_data:
            self._load_tool_parameters(tool_data)
            self.test_btn.setEnabled(True)
    
    def _load_tool_parameters(self, tool_data: dict):
        """Načítaj parametre nástroja do tabuľky."""
        parameters = tool_data.get("parameters", {})
        self.params_table.setRowCount(len(parameters))
        
        for row, (param_name, param_type) in enumerate(parameters.items()):
            self.params_table.setItem(row, 0, QTableWidgetItem(param_name))
            self.params_table.setItem(row, 1, QTableWidgetItem(param_type))
            
            # Default hodnota podľa typu
            default_value = ""
            if param_type == "boolean":
                default_value = "true"
            elif param_type == "number":
                default_value = "0"
            elif param_type == "array":
                default_value = "[]"
            
            self.params_table.setItem(row, 2, QTableWidgetItem(default_value))
    
    def _add_parameter(self):
        """Pridať nový parameter."""
        row_count = self.params_table.rowCount()
        self.params_table.insertRow(row_count)
        self.params_table.setItem(row_count, 0, QTableWidgetItem(""))
        self.params_table.setItem(row_count, 1, QTableWidgetItem("string"))
        self.params_table.setItem(row_count, 2, QTableWidgetItem(""))
    
    def _remove_parameter(self):
        """Odstrániť vybraný parameter."""
        current_row = self.params_table.currentRow()
        if current_row >= 0:
            self.params_table.removeRow(current_row)
    
    def _run_tool_test(self):
        """Spusti test nástroja."""
        server_name = self.tool_server_combo.currentText()
        tool_name = self.tool_combo.currentText()
        
        if not server_name or not tool_name:
            return
        
        # Zbieraj parametre z tabuľky
        parameters = {}
        for row in range(self.params_table.rowCount()):
            param_name = self.params_table.item(row, 0)
            param_value = self.params_table.item(row, 2)
            
            if param_name and param_value:
                param_name = param_name.text().strip()
                param_value = param_value.text().strip()
                
                if param_name and param_value:
                    # Skús parsovať hodnotu podľa typu
                    try:
                        param_type = self.params_table.item(row, 1).text()
                        if param_type == "boolean":
                            parameters[param_name] = param_value.lower() in ("true", "1", "yes")
                        elif param_type == "number":
                            parameters[param_name] = int(param_value)
                        elif param_type == "array":
                            parameters[param_name] = json.loads(param_value)
                        else:
                            parameters[param_name] = param_value
                    except (ValueError, json.JSONDecodeError):
                        parameters[param_name] = param_value
        
        # Spusti worker pre test
        worker = MCPToolTestWorker(tool_name, parameters, server_name)
        worker.test_result.connect(self._on_test_result)
        worker.log_message.connect(self._log_message)
        
        self.workers[f"test_{tool_name}"] = worker
        worker.start()
        
        self.test_btn.setEnabled(False)
        self.status_label.setText(f"Testujem nástroj: {tool_name}")
    
    def _on_test_result(self, result: dict):
        """Spracuj výsledok testu nástroja."""
        tool_name = result["tool_name"]
        success = result["success"]
        test_result = result["result"]
        error = result["error"]
        
        if success:
            self.results_text.setPlainText(json.dumps(test_result, indent=2, ensure_ascii=False))
            self._log_message(f"✅ Test nástroja '{tool_name}' úspešný")
            self.status_label.setText(f"Test '{tool_name}' úspešný")
        else:
            self.results_text.setPlainText(f"Chyba: {error}")
            self._log_message(f"❌ Test nástroja '{tool_name}' zlyhal: {error}")
            self.status_label.setText(f"Test '{tool_name}' zlyhal")
        
        self.test_btn.setEnabled(True)
        
        # Vyčisti worker
        worker_key = f"test_{tool_name}"
        if worker_key in self.workers:
            del self.workers[worker_key]
    
    def _log_message(self, message: str):
        """Pridať správu do logu."""
        from datetime import datetime
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {message}"
        
        # Log do konzoly
        log.info(message)
        
        # Log do UI ak je logs dialog vytvorený
        if hasattr(self, 'logs_text') and self.logs_text:
            self.logs_text.append(log_entry)
            
            # Auto-scroll ak je povolené
            if hasattr(self, 'auto_scroll_check') and self.auto_scroll_check.isChecked():
                cursor = self.logs_text.textCursor()
                cursor.movePosition(QTextCursor.MoveOperation.End)
                self.logs_text.setTextCursor(cursor)
    
    def _clear_logs(self):
        """Vymazať logy."""
        if hasattr(self, 'logs_text') and self.logs_text:
            self.logs_text.clear()
            self._log_message("🗑️ Logy vymazané")
    
    def _save_logs(self):
        """Uložiť logy do súboru."""
        if not hasattr(self, 'logs_text') or not self.logs_text:
            return
            
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Uložiť logy", "mcp_test_logs.txt", "Text súbory (*.txt)"
        )
        
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(self.logs_text.toPlainText())
                self._log_message(f"💾 Logy uložené do: {file_path}")
            except Exception as e:
                QMessageBox.critical(self, "Chyba", f"Nepodarilo sa uložiť logy: {e}")
    
    def _on_server_selected(self, server_name: str):
        """Spracuj výber servera z dropdown."""
        if server_name and server_name in self.saved_servers:
            config = self.saved_servers[server_name]
            self._load_server_config(config)
            self.config_group.setVisible(True)
            self.connect_btn.setEnabled(True)
            self.delete_server_btn.setEnabled(True)
            self.rename_server_btn.setEnabled(True)
        else:
            self.config_group.setVisible(False)
            self.connect_btn.setEnabled(False)
            self.delete_server_btn.setEnabled(False)
            self.rename_server_btn.setEnabled(False)
    
    def _on_connection_type_changed(self, connection_type: str):
        """Spracuj zmenu typu pripojenia."""
        is_command = connection_type == "Príkaz (Command)"
        
        # Show/hide command fields
        self.command_label.setVisible(is_command)
        self.command_edit.setVisible(is_command)
        self.args_label.setVisible(is_command)
        self.args_edit.setVisible(is_command)
        
        # Show/hide URL fields
        self.url_label.setVisible(not is_command)
        self.url_edit.setVisible(not is_command)
        self.port_label.setVisible(not is_command)
        self.port_edit.setVisible(not is_command)
    
    def _show_add_server_dialog(self):
        """Zobraz dialóg pre pridanie nového servera."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Pridať MCP Server")
        dialog.setModal(True)
        dialog.resize(500, 400)
        
        # Apply dark forest theme
        dialog.setStyleSheet("""
            QDialog {
                background-color: #0f1a12;
                color: #e8f5e9;
            }
            QLabel {
                color: #e8f5e9;
            }
            QLineEdit {
                background: #000000;
                color: #e8f5e9;
                border: 1px solid #2f5c39;
                border-radius: 4px;
                padding: 6px 8px;
                font-size: 12px;
            }
            QLineEdit:hover {
                border-color: #4caf50;
            }
            QLineEdit:focus {
                border-color: #4caf50;
                background: #0a0a0a;
            }
            QComboBox {
                background: #000000;
                color: #e8f5e9;
                border: 1px solid #2f5c39;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 12px;
            }
            QComboBox:hover {
                border-color: #4caf50;
                background: #0a0a0a;
            }
            QComboBox:focus {
                border-color: #4caf50;
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
            QComboBox QAbstractItemView {
                background: #000000;
                color: #e8f5e9;
                selection-background-color: #295c33;
                border: 1px solid #2f5c39;
            }
            QPushButton {
                background: #1a2f1f;
                color: #e8f5e9;
                border: 1px solid #2f5c39;
                border-radius: 4px;
                padding: 6px 12px;
                font-size: 12px;
            }
            QPushButton:hover {
                background: #213f29;
                border-color: #4caf50;
            }
            QPushButton:pressed {
                background: #152820;
            }
        """)
        
        layout = QVBoxLayout(dialog)
        
        # Form
        form_layout = QFormLayout()
        
        # Server name
        name_edit = QLineEdit()
        name_edit.setPlaceholderText("Názov servera")
        form_layout.addRow("Názov servera:", name_edit)
        
        # Connection type
        connection_type_combo = QComboBox()
        connection_type_combo.addItems(["Príkaz (Command)", "URL + Port"])
        form_layout.addRow("Typ pripojenia:", connection_type_combo)
        
        # Command fields (default visible)
        command_label = QLabel("Príkaz:")
        command_edit = QLineEdit()
        command_edit.setPlaceholderText("Príkaz (napr. poetry)")
        form_layout.addRow(command_label, command_edit)
        
        args_label = QLabel("Argumenty:")
        args_edit = QLineEdit()
        args_edit.setPlaceholderText("Argumenty oddelené čiarkou")
        form_layout.addRow(args_label, args_edit)
        
        # URL fields (hidden by default)
        url_label = QLabel("URL:")
        url_edit = QLineEdit()
        url_edit.setPlaceholderText("URL (napr. localhost)")
        url_label.setVisible(False)
        url_edit.setVisible(False)
        form_layout.addRow(url_label, url_edit)
        
        port_label = QLabel("Port:")
        port_edit = QLineEdit()
        port_edit.setPlaceholderText("Port (napr. 8080)")
        port_label.setVisible(False)
        port_edit.setVisible(False)
        form_layout.addRow(port_label, port_edit)
        
        # Description
        description_edit = QLineEdit()
        description_edit.setPlaceholderText("Popis servera")
        form_layout.addRow("Popis:", description_edit)
        
        # Load config button
        load_config_btn = QPushButton("📁 Načítať konfiguráciu")
        load_config_btn.clicked.connect(lambda: self._load_config_to_dialog(dialog, name_edit, command_edit, args_edit, description_edit))
        form_layout.addRow("", load_config_btn)
        
        layout.addLayout(form_layout)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        cancel_btn = QPushButton("Zrušiť")
        cancel_btn.clicked.connect(dialog.reject)
        button_layout.addWidget(cancel_btn)
        
        button_layout.addStretch()
        
        ok_btn = QPushButton("Pridať")
        ok_btn.clicked.connect(lambda: self._add_server_from_dialog(
            dialog, name_edit, connection_type_combo, command_edit, args_edit, 
            url_edit, port_edit, description_edit
        ))
        button_layout.addWidget(ok_btn)
        
        layout.addLayout(button_layout)
        
        # Connection type change handler
        def on_connection_type_changed(connection_type: str):
            is_command = connection_type == "Príkaz (Command)"
            
            # Show/hide command fields
            command_label.setVisible(is_command)
            command_edit.setVisible(is_command)
            args_label.setVisible(is_command)
            args_edit.setVisible(is_command)
            
            # Show/hide URL fields
            url_label.setVisible(not is_command)
            url_edit.setVisible(not is_command)
            port_label.setVisible(not is_command)
            port_edit.setVisible(not is_command)
        
        connection_type_combo.currentTextChanged.connect(on_connection_type_changed)
        
        dialog.exec()
    
    def _load_config_to_dialog(self, dialog, name_edit, command_edit, args_edit, description_edit):
        """Načítaj konfiguráciu do dialógu."""
        file_path, _ = QFileDialog.getOpenFileName(
            dialog, "Načítať MCP konfiguráciu", "", "JSON súbory (*.json)"
        )
        
        if file_path:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                
                # Načítaj prvý server z konfigurácie
                servers = config.get("mcpServers", {})
                if servers:
                    server_name, server_config = next(iter(servers.items()))
                    name_edit.setText(server_name)
                    command_edit.setText(server_config.get("command", ""))
                    args_edit.setText(", ".join(server_config.get("args", [])))
                    description_edit.setText(server_config.get("description", ""))
                    
                    self._log_message(f"📁 Načítaná konfigurácia: {file_path}")
                else:
                    QMessageBox.warning(dialog, "Chyba", "Konfigurácia neobsahuje žiadne servery")
                    
            except Exception as e:
                QMessageBox.critical(dialog, "Chyba", f"Nepodarilo sa načítať konfiguráciu: {e}")
    
    def _add_server_from_dialog(self, dialog, name_edit, connection_type_combo, command_edit, args_edit, url_edit, port_edit, description_edit):
        """Pridať server z dialógu."""
        server_name = name_edit.text().strip()
        if not server_name:
            QMessageBox.warning(dialog, "Chyba", "Zadajte názov servera")
            return
        
        if server_name in self.saved_servers:
            QMessageBox.warning(dialog, "Chyba", f"Server '{server_name}' už existuje")
            return
        
        # Vytvor konfiguráciu
        connection_type = connection_type_combo.currentText()
        if connection_type == "Príkaz (Command)":
            config = {
                "type": "command",
                "command": command_edit.text().strip(),
                "args": [arg.strip() for arg in args_edit.text().split(",") if arg.strip()],
                "description": description_edit.text().strip()
            }
        else:  # URL + Port
            config = {
                "type": "url",
                "url": url_edit.text().strip(),
                "port": int(port_edit.text().strip()) if port_edit.text().strip() else 8080,
                "description": description_edit.text().strip()
            }
        
        self.saved_servers[server_name] = config
        self._update_server_dropdown()
        self._log_message(f"➕ Pridaný server: {server_name}")
        
        dialog.accept()
    
    def _delete_server(self):
        """Zmazať vybraný server."""
        server_name = self.server_dropdown.currentText()
        if not server_name:
            return
        
        reply = QMessageBox.question(
            self, "Potvrdiť zmazanie", 
            f"Naozaj chcete zmazať server '{server_name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            del self.saved_servers[server_name]
            self._update_server_dropdown()
            self.config_group.setVisible(False)
            self._log_message(f"🗑️ Zmazaný server: {server_name}")
    
    def _rename_server(self):
        """Premenovať vybraný server."""
        old_name = self.server_dropdown.currentText()
        if not old_name:
            return
        
        new_name, ok = QInputDialog.getText(
            self, "Premenovať server", "Nový názov servera:", text=old_name
        )
        
        if ok and new_name and new_name != old_name:
            if new_name in self.saved_servers:
                QMessageBox.warning(self, "Chyba", f"Server '{new_name}' už existuje")
                return
            
            config = self.saved_servers[old_name]
            del self.saved_servers[old_name]
            self.saved_servers[new_name] = config
            
            self._update_server_dropdown()
            self.server_dropdown.setCurrentText(new_name)
            self._log_message(f"✎ Premenovaný server: {old_name} → {new_name}")
    
    def _update_server_dropdown(self):
        """Aktualizuj dropdown serverov."""
        self.server_dropdown.clear()
        for server_name in sorted(self.saved_servers.keys()):
            self.server_dropdown.addItem(server_name)
    
    def _load_server_config(self, config: dict):
        """Načítaj konfiguráciu servera do formulára."""
        self.server_name_edit.setText(config.get("name", ""))
        self.description_edit.setText(config.get("description", ""))
        
        if config.get("type") == "url":
            self.connection_type_combo.setCurrentText("URL + Port")
            self.url_edit.setText(config.get("url", ""))
            self.port_edit.setText(str(config.get("port", 8080)))
        else:
            self.connection_type_combo.setCurrentText("Príkaz (Command)")
            self.command_edit.setText(config.get("command", ""))
            self.args_edit.setText(", ".join(config.get("args", [])))
    
    def _open_logs_dialog(self):
        """Otvoriť dialóg s logmi."""
        if self.logs_dialog is None:
            self.logs_dialog = QDialog(self)
            self.logs_dialog.setWindowTitle("📋 MCP Logy")
            self.logs_dialog.setModal(False)
            self.logs_dialog.resize(800, 600)
            
            # Apply dark forest theme
            self.logs_dialog.setStyleSheet("""
                QDialog {
                    background-color: #0f1a12;
                    color: #e8f5e9;
                }
                QLabel {
                    color: #e8f5e9;
                }
                QTextEdit {
                    background: #000000;
                    color: #e8f5e9;
                    border: 1px solid #2f5c39;
                    border-radius: 4px;
                    padding: 8px;
                    font-family: 'Monospace', 'Courier New';
                    font-size: 11px;
                }
                QTextEdit:hover {
                    border-color: #4caf50;
                }
                QTextEdit:focus {
                    border-color: #4caf50;
                    background: #0a0a0a;
                }
                QPushButton {
                    background: #1a2f1f;
                    color: #e8f5e9;
                    border: 1px solid #2f5c39;
                    border-radius: 4px;
                    padding: 6px 12px;
                    font-size: 12px;
                }
                QPushButton:hover {
                    background: #213f29;
                    border-color: #4caf50;
                }
                QPushButton:pressed {
                    background: #152820;
                }
                QCheckBox {
                    color: #e8f5e9;
                }
                QCheckBox:hover {
                    color: #4caf50;
                }
            """)
            
            layout = QVBoxLayout(self.logs_dialog)
            
            # Log controls
            controls_layout = QHBoxLayout()
            
            clear_logs_btn = QPushButton("🗑️ Vymazať logy")
            clear_logs_btn.clicked.connect(self._clear_logs)
            controls_layout.addWidget(clear_logs_btn)
            
            save_logs_btn = QPushButton("💾 Uložiť logy")
            save_logs_btn.clicked.connect(self._save_logs)
            controls_layout.addWidget(save_logs_btn)
            
            self.auto_scroll_check = QCheckBox("Automatické posúvanie")
            self.auto_scroll_check.setChecked(True)
            controls_layout.addWidget(self.auto_scroll_check)
            
            controls_layout.addStretch()
            layout.addLayout(controls_layout)
            
            # Logs display
            self.logs_text = QTextEdit()
            self.logs_text.setReadOnly(True)
            font = QFont("Monospace")
            font.setPointSize(10)
            self.logs_text.setFont(font)
            layout.addWidget(self.logs_text)
        
        self.logs_dialog.show()
        self.logs_dialog.raise_()
        self.logs_dialog.activateWindow()
    
    # ==================== Agent Chat Tab ====================
    
    def _create_chat_tab(self) -> QWidget:
        """Vytvor tab pre agent chat s unified flow."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)
        
        # Config section
        config_group = self._create_chat_config_section()
        layout.addWidget(config_group)
        
        # Split panel: Main chat (70%) + Reasoning detail (30%)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Main chat panel (unified flow)
        chat_panel = self._create_unified_chat_panel()
        splitter.addWidget(chat_panel)
        
        # Reasoning detail panel (collapsible)
        reasoning_panel = self._create_reasoning_detail_panel()
        splitter.addWidget(reasoning_panel)
        
        # Set stretch factors
        splitter.setStretchFactor(0, 70)
        splitter.setStretchFactor(1, 30)
        
        layout.addWidget(splitter, stretch=1)
        
        return widget
    
    def _create_chat_config_section(self) -> QGroupBox:
        """Vytvor konfiguračnú sekciu."""
        group = QGroupBox("🤖 Agent Konfigurácia")
        group.setStyleSheet("""
            QGroupBox {
                background: #111a13;
                border: 1px solid #243227;
                border-radius: 8px;
                margin-top: 8px;
                padding: 10px;
                font-family: 'Fira Sans', 'Segoe UI', sans-serif;
                color: #e8e3d9;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 4px;
            }
            QLabel {
                color: #e8e3d9;
                font-family: 'Fira Sans', 'Segoe UI', sans-serif;
            }
        """)
        layout = QFormLayout(group)
        
        # Server URL (klikateľný)
        url_layout = QHBoxLayout()
        self.chat_server_url = ClickableLabel("127.0.0.1:1234")
        self.chat_server_url.clicked.connect(self._edit_chat_server_url)
        self.chat_server_url.setCursor(Qt.CursorShape.PointingHandCursor)
        self.chat_server_url.setStyleSheet(
            "color: #e8e3d9; text-decoration: underline; "
            "padding: 6px 8px; background: #0f1812; border: 1px solid #324536; "
            "border-radius: 6px;"
        )
        self.chat_server_url.setToolTip("Kliknite pre editáciu")
        url_layout.addWidget(self.chat_server_url)
        
        edit_url_btn = QPushButton("📝")
        edit_url_btn.setMaximumWidth(40)
        edit_url_btn.clicked.connect(self._edit_chat_server_url)
        url_layout.addWidget(edit_url_btn)
        url_layout.addStretch()
        
        layout.addRow("Server URL:", url_layout)
        
        # Model (klikateľný)
        model_layout = QHBoxLayout()
        self.chat_model_name = ClickableLabel("deepseek/deepseek-r1-0528-qwen3-8b")
        self.chat_model_name.clicked.connect(self._edit_chat_model)
        self.chat_model_name.setCursor(Qt.CursorShape.PointingHandCursor)
        self.chat_model_name.setStyleSheet(
            "color: #e8e3d9; text-decoration: underline; "
            "padding: 6px 8px; background: #0f1812; border: 1px solid #324536; "
            "border-radius: 6px;"
        )
        self.chat_model_name.setToolTip("Kliknite pre editáciu")
        model_layout.addWidget(self.chat_model_name)
        model_layout.addStretch()
        
        layout.addRow("Model:", model_layout)
        
        # Options row
        options_layout = QHBoxLayout()
        
        self.chat_context_checkbox = QCheckBox("Context Session")
        self.chat_context_checkbox.setChecked(True)
        self.chat_context_checkbox.setToolTip("Použiť context session pre úsporu tokenov")
        options_layout.addWidget(self.chat_context_checkbox)
        
        self.chat_auto_execute = QCheckBox("Auto-execute Tools")
        self.chat_auto_execute.setChecked(True)
        self.chat_auto_execute.setToolTip("Automaticky vykonávať tool calls")
        options_layout.addWidget(self.chat_auto_execute)
        
        options_layout.addWidget(QLabel("History:"))
        self.chat_history_spinbox = QSpinBox()
        self.chat_history_spinbox.setRange(1, 20)
        self.chat_history_spinbox.setValue(8)
        self.chat_history_spinbox.setMaximumWidth(60)
        options_layout.addWidget(self.chat_history_spinbox)
        
        options_layout.addStretch()
        layout.addRow("", options_layout)
        
        # Tools info
        tools_layout = QHBoxLayout()
        self.chat_tools_label = QLabel("Available Tools: 0")
        self.chat_tools_label.setStyleSheet("color: #ff9800;")
        tools_layout.addWidget(self.chat_tools_label)
        
        refresh_tools_btn = QPushButton("🔄 Refresh")
        refresh_tools_btn.clicked.connect(self._refresh_chat_tools)
        refresh_tools_btn.setMaximumWidth(100)
        tools_layout.addWidget(refresh_tools_btn)
        
        tools_layout.addStretch()
        layout.addRow("", tools_layout)
        
        # Connect buttons + status
        button_layout = QHBoxLayout()
        
        self.chat_connect_btn = QPushButton("🔌 Pripojiť")
        self.chat_connect_btn.clicked.connect(self._connect_chat_server)
        button_layout.addWidget(self.chat_connect_btn)
        
        self.chat_disconnect_btn = QPushButton("🔌 Odpojiť")
        self.chat_disconnect_btn.clicked.connect(self._disconnect_chat_server)
        self.chat_disconnect_btn.setEnabled(False)
        button_layout.addWidget(self.chat_disconnect_btn)
        
        button_layout.addStretch()
        
        # Status indicator
        self.chat_status_indicator = QLabel("●")
        self.chat_status_indicator.setStyleSheet("color: #666; font-size: 16px;")
        button_layout.addWidget(self.chat_status_indicator)
        
        self.chat_status_text = QLabel("Pripravené")
        self.chat_status_text.setStyleSheet("color: #666;")
        button_layout.addWidget(self.chat_status_text)
        
        layout.addRow("", button_layout)
        
        return group
    
    def _create_unified_chat_panel(self) -> QWidget:
        """Vytvor unified chat panel kde je všetko pohromade."""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setSpacing(8)
        layout.setContentsMargins(8, 8, 8, 8)
        
        # Header
        header_layout = QHBoxLayout()
        header = QLabel("💬 Agent Chat - Unified Flow")
        header.setStyleSheet(
            "color: #e8e3d9; font-weight: bold; font-size: 14px; "
            "font-family: 'Fira Sans', 'Segoe UI', sans-serif;"
        )
        header_layout.addWidget(header)
        
        # Message counter
        self.chat_message_counter = QLabel("Messages: 0")
        self.chat_message_counter.setStyleSheet(
            "color: #a6ad9c; font-size: 11px; font-family: 'Fira Sans', 'Segoe UI', sans-serif;"
        )
        header_layout.addWidget(self.chat_message_counter)
        
        header_layout.addStretch()
        
        clear_btn = QPushButton("🗑️ Vyčistiť")
        clear_btn.clicked.connect(self._clear_chat_history)
        clear_btn.setMaximumWidth(100)
        header_layout.addWidget(clear_btn)
        
        layout.addLayout(header_layout)
        
        # Chat display (HTML formatted, all-in-one) - with click handling
        self.chat_display = ClickableChatDisplay()
        self.chat_display.setReadOnly(True)
        self.chat_display.setStyleSheet("""
            QTextEdit {
                background: #0f1812;
                color: #e8e3d9;
                border: 1px solid #243227;
                border-radius: 8px;
                padding: 12px;
                font-size: 12px;
                line-height: 1.4;
                font-family: 'Fira Sans', 'Segoe UI', sans-serif;
            }
        """)
        self.chat_display.message_clicked.connect(self._on_message_clicked)
        layout.addWidget(self.chat_display, stretch=1)
        
        # Input section
        input_layout = QHBoxLayout()
        
        self.chat_input = QLineEdit()
        self.chat_input.setPlaceholderText("Napíšte správu agentovi... (Enter pre odoslanie)")
        self.chat_input.returnPressed.connect(self._send_chat_message)
        self.chat_input.setStyleSheet("""
            QLineEdit {
                padding: 10px 12px;
                font-size: 13px;
                border-radius: 8px;
                border: 1px solid #324536;
                background: #0f1812;
                color: #e8e3d9;
                font-family: 'Fira Sans', 'Segoe UI', sans-serif;
            }
            QLineEdit:focus {
                border: 1px solid #5fbcbc;
                background: #132119;
            }
        """)
        input_layout.addWidget(self.chat_input, stretch=1)
        
        self.chat_send_btn = QPushButton("📤 Odoslať")
        self.chat_send_btn.clicked.connect(self._send_chat_message)
        self.chat_send_btn.setMinimumWidth(100)
        self.chat_send_btn.setStyleSheet("""
            QPushButton {
                background: #d64b3e;
                color: #fdfbf5;
                border: 1px solid #9f332c;
                border-radius: 8px;
                padding: 10px 14px;
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
        input_layout.addWidget(self.chat_send_btn)
        
        layout.addLayout(input_layout)
        
        return panel
    
    def _create_reasoning_detail_panel(self) -> QWidget:
        """Vytvor panel pre detailné zobrazenie reasoning (voliteľné)."""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setSpacing(8)
        layout.setContentsMargins(8, 8, 8, 8)
        
        # Header
        header_layout = QHBoxLayout()
        header = QLabel("🧠 Reasoning Detail")
        header.setStyleSheet(
            "color: #e8e3d9; font-weight: bold; font-size: 14px; "
            "font-family: 'Fira Sans', 'Segoe UI', sans-serif;"
        )
        header_layout.addWidget(header)
        header_layout.addStretch()
        
        clear_btn = QPushButton("🗑️")
        clear_btn.setMaximumWidth(40)
        clear_btn.clicked.connect(self._clear_reasoning_detail)
        clear_btn.setToolTip("Vyčistiť reasoning panel")
        header_layout.addWidget(clear_btn)
        
        layout.addLayout(header_layout)
        
        # Reasoning display (monospace, for detailed inspection)
        self.reasoning_detail_display = QTextEdit()
        self.reasoning_detail_display.setReadOnly(True)
        self.reasoning_detail_display.setStyleSheet("""
            QTextEdit {
                background: #0f1812;
                color: #e8e3d9;
                border: 1px solid #243227;
                border-radius: 8px;
                padding: 10px;
                font-family: 'Fira Code', 'Consolas', monospace;
                font-size: 11px;
            }
        """)
        self.reasoning_detail_display.setPlaceholderText(
            "Reasoning obsah sa zobrazí tu po prijatí odpovede od agenta..."
        )
        layout.addWidget(self.reasoning_detail_display, stretch=1)
        
        # Auto-scroll
        self.reasoning_auto_scroll = QCheckBox("Auto-scroll")
        self.reasoning_auto_scroll.setChecked(True)
        layout.addWidget(self.reasoning_auto_scroll)
        
        return panel
    
    def _append_chat_message(self, role: str, content: str, msg_type: str = "text", extra_data: dict = None):
        """Pridaj správu do unified chatu s HTML formátovaním a click handling."""
        cursor = self.chat_display.textCursor()
        start_position = cursor.position()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        # Track request number for user messages
        if msg_type == "user":
            self.chat_request_counter += 1
        
        request_num = self.chat_request_counter
        
        if msg_type == "user":
            # User message - zelená s request number
            cursor.insertHtml(
                f'<div style="margin: 16px 0 4px 0; padding: 10px; '
                f'background: #1a2f1f; border-left: 4px solid #4caf50; border-radius: 4px;">'
                f'<div style="margin-bottom: 4px;">'
                f'<span style="color: #4caf50; font-weight: bold; font-size: 13px;">👤 User</span> '
                f'<span style="color: #4caf50; font-size: 11px; margin-left: 8px; '
                f'background: #0a2f0a; padding: 2px 6px; border-radius: 3px;">#{request_num}</span> '
                f'<span style="color: #666; font-size: 10px; margin-left: 8px;">{timestamp}</span>'
                f'</div>'
                f'<div style="color: #e8f5e9; font-size: 13px; line-height: 1.5;">{html.escape(content)}</div>'
                f'</div>'
            )
        
        elif msg_type == "tool_call":
            # Tool call - oranžový s ikonou
            tool_name = extra_data.get("tool_name", "unknown") if extra_data else "unknown"
            args = extra_data.get("args", {}) if extra_data else {}
            args_str = json.dumps(args, indent=2, ensure_ascii=False)
            
            cursor.insertHtml(
                f'<div style="margin: 8px 0 8px 20px; padding: 10px; '
                f'background: #2f1f0a; border-left: 4px solid #ff6f00; border-radius: 4px;">'
                f'<div style="margin-bottom: 4px;">'
                f'<span style="color: #ff9800; font-weight: bold; font-size: 12px;">🔧 Tool Call</span> '
                f'<span style="color: #ffb74d; font-size: 12px; margin-left: 8px;">{tool_name}()</span> '
                f'<span style="color: #666; font-size: 10px; margin-left: 8px;">{timestamp}</span>'
                f'</div>'
                f'<pre style="color: #ffb74d; font-family: monospace; font-size: 11px; '
                f'white-space: pre-wrap; margin: 0; line-height: 1.4;">{html.escape(args_str)}</pre>'
                f'</div>'
            )
        
        elif msg_type == "tool_result":
            # Tool result - zelená/červená
            is_success = extra_data.get("status") == "success" if extra_data else True
            result = extra_data.get("result") if extra_data else content
            error = extra_data.get("error") if extra_data else None
            
            color = "#4caf50" if is_success else "#f44336"
            bg_color = "#1a2f1a" if is_success else "#2f1a1a"
            icon = "✅" if is_success else "❌"
            
            if is_success:
                result_str = json.dumps(result, indent=2, ensure_ascii=False) if isinstance(result, (dict, list)) else str(result)
            else:
                result_str = error or "Unknown error"
            
            cursor.insertHtml(
                f'<div style="margin: 8px 0 8px 20px; padding: 10px; '
                f'background: {bg_color}; border-left: 4px solid {color}; border-radius: 4px;">'
                f'<div style="margin-bottom: 4px;">'
                f'<span style="color: {color}; font-weight: bold; font-size: 12px;">{icon} Tool Result</span> '
                f'<span style="color: #666; font-size: 10px; margin-left: 8px;">{timestamp}</span>'
                f'</div>'
                f'<pre style="color: {color}; font-family: monospace; font-size: 11px; '
                f'white-space: pre-wrap; margin: 0; line-height: 1.4;">{html.escape(result_str)}</pre>'
                f'</div>'
            )
        
        elif msg_type == "assistant":
            # Assistant message - modrá s response indicator
            has_thinking = extra_data and extra_data.get("thinking")
            thinking_indicator = " 💭" if has_thinking else ""
            cursor_style = "cursor: pointer;" if has_thinking else ""
            hover_hint = " (kliknite pre zobrazenie thinking)" if has_thinking else ""
            msg_id = f"msg_{timestamp.replace(':', '')}_{id(content)}"
            
            # Store thinking and position for click handling
            if has_thinking:
                self.chat_display._message_thinking_map[msg_id] = extra_data["thinking"]
            
            before_insert = cursor.position()
            
            # Build hint HTML separately to avoid escaping issues
            hint_html = ""
            if has_thinking:
                hint_html = (
                    '<span style="color: #666; font-size: 10px; margin-left: 8px; font-style: italic;">'
                    + hover_hint + '</span>'
                )
            
            cursor.insertHtml(
                f'<div style="margin: 4px 0 16px 0; padding: 10px; '
                f'background: #1a1f2f; border-left: 4px solid #64b5f6; border-radius: 4px; {cursor_style} '
                f'transition: background 0.2s;">'
                f'<div style="margin-bottom: 4px;">'
                f'<span style="color: #64b5f6; font-weight: bold; font-size: 13px;">🤖 Assistant{thinking_indicator}</span> '
                f'<span style="color: #64b5f6; font-size: 11px; margin-left: 8px; '
                f'background: #0a1f2f; padding: 2px 6px; border-radius: 3px;">→ #{request_num}</span> '
                f'<span style="color: #666; font-size: 10px; margin-left: 8px;">{timestamp}</span>'
                f'{hint_html}'
                f'</div>'
                f'<div style="color: #e8f5e9; font-size: 13px; line-height: 1.5;">{html.escape(content)}</div>'
                f'</div>'
            )
            after_insert = cursor.position()
            
            # Store message position for click detection
            if has_thinking:
                self.chat_display._message_positions[msg_id] = (before_insert, after_insert)
        
        # Auto-scroll
        self.chat_display.setTextCursor(cursor)
        self.chat_display.ensureCursorVisible()
        
        # Update message counter
        total_messages = len(self.chat_display._message_positions) + self.chat_request_counter
        self.chat_message_counter.setText(f"Messages: {total_messages}")
    
    def _append_reasoning_detail(self, content: str):
        """Pridaj reasoning do detail panelu s typing efektom ako OpenAI/Claude."""
        # Clear any ongoing animation
        if self.thinking_timer:
            self.thinking_timer.stop()
            self.thinking_timer = None
        
        # Prepare header
        cursor = self.reasoning_detail_display.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        
        cursor.insertHtml(
            f'<div style="color: #4caf50; font-weight: bold; margin-top: 12px;">'
            f'💭 Thinking Stream</div>'
            f'<div style="color: #666; font-size: 11px; margin-bottom: 8px;">'
            f'[{timestamp}]</div>'
        )
        
        # Start typing animation
        self.thinking_text = content
        self.thinking_position = 0
        self.thinking_timer = QTimer(self)
        self.thinking_timer.timeout.connect(self._update_thinking_animation)
        self.thinking_timer.start(20)  # Update every 20ms for smooth typing
        
        self.reasoning_detail_display.setTextCursor(cursor)
    
    def _update_thinking_animation(self):
        """Update thinking typing effect - progresívne reveal ako OpenAI."""
        if self.thinking_position >= len(self.thinking_text):
            # Finished
            if self.thinking_timer:
                self.thinking_timer.stop()
                self.thinking_timer = None
            # Auto-scroll at end
            if self.reasoning_auto_scroll.isChecked():
                cursor = self.reasoning_detail_display.textCursor()
                cursor.movePosition(QTextCursor.MoveOperation.End)
                self.reasoning_detail_display.setTextCursor(cursor)
                self.reasoning_detail_display.ensureCursorVisible()
            return
        
        # Add next chunk of text
        end_pos = min(self.thinking_position + self.thinking_speed, len(self.thinking_text))
        chunk = self.thinking_text[self.thinking_position:end_pos]
        
        cursor = self.reasoning_detail_display.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        
        # Insert text with blinking cursor simulation
        cursor.insertText(chunk)
        
        # Add temporary blinking cursor at the end
        if end_pos < len(self.thinking_text):
            cursor.insertHtml('<span style="color: #4caf50;">▋</span>')
            # Remove cursor on next iteration (store position to remove)
            QTimer.singleShot(10, lambda: self._remove_typing_cursor())
        
        self.thinking_position = end_pos
        self.reasoning_detail_display.setTextCursor(cursor)
        
        # Auto-scroll during typing
        if self.reasoning_auto_scroll.isChecked():
            self.reasoning_detail_display.ensureCursorVisible()
    
    def _remove_typing_cursor(self):
        """Odstráň blikajúci kurzor z typing animácie."""
        cursor = self.reasoning_detail_display.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        
        # Move back and remove the cursor character if present
        for _ in range(1):
            cursor.movePosition(QTextCursor.MoveOperation.Left, QTextCursor.MoveMode.KeepAnchor)
        
        selected = cursor.selectedText()
        if '▋' in selected:
            cursor.removeSelectedText()
        else:
            cursor.clearSelection()
    
    # Connection and message handling
    
    def _edit_chat_server_url(self):
        """Edit server URL."""
        current = self.chat_server_url.text()
        text, ok = QInputDialog.getText(
            self, "Edit Server URL", 
            "Server URL (IP:port):", 
            QLineEdit.EchoMode.Normal,
            current
        )
        if ok and text:
            self.chat_server_url.setText(text)
    
    def _edit_chat_model(self):
        """Edit model name."""
        current = self.chat_model_name.text()
        text, ok = QInputDialog.getText(
            self, "Edit Model", 
            "Model name:", 
            QLineEdit.EchoMode.Normal,
            current
        )
        if ok and text:
            self.chat_model_name.setText(text)
    
    def _refresh_chat_tools(self):
        """Refresh available tools."""
        try:
            self.chat_available_functions = _get_available_functions()
            count = len(self.chat_available_functions)
            self.chat_tools_label.setText(f"Available Tools: {count}")
            log.info(f"Refreshed {count} tools for agent chat")
        except Exception as e:
            log.exception("Failed to refresh tools")
            QMessageBox.warning(self, "Tools", f"Chyba pri načítaní tools: {e}")
    
    def _connect_chat_server(self):
        """Pripoj sa k reasoning serveru."""
        try:
            server_url = self.chat_server_url.text()
            model = self.chat_model_name.text()
            
            if not server_url or not model:
                QMessageBox.warning(self, "Agent Chat", "Vyplňte server URL a model!")
                return
            
            # Set environment variables
            os.environ["OPENAI_BASE_URL"] = f"http://{server_url}/v1"
            os.environ["OPENAI_MODEL"] = model
            
            if self.chat_context_checkbox.isChecked():
                os.environ["AI_CONTEXT_SESSION"] = "1"
                os.environ["AI_CONTEXT_HISTORY"] = str(self.chat_history_spinbox.value())
            else:
                os.environ.pop("AI_CONTEXT_SESSION", None)
            
            # Create client
            self.chat_client = OpenAIClient(model=model)
            
            # Refresh tools
            self._refresh_chat_tools()
            
            # Update UI
            self._set_chat_status("connected", "Pripojené")
            self.chat_connect_btn.setEnabled(False)
            self.chat_disconnect_btn.setEnabled(True)
            self.chat_input.setEnabled(True)
            self.chat_send_btn.setEnabled(True)
            
            # System message
            self._append_chat_message("System", 
                f"🟢 Pripojené k serveru {server_url} s modelom {model}", 
                "assistant")
            
            log.info(f"Connected to agent chat: {server_url} / {model}")
            
        except Exception as e:
            log.exception("Chat connection failed")
            self._set_chat_status("error", f"Chyba: {e}")
            QMessageBox.critical(self, "Agent Chat", f"Nepodarilo sa pripojiť: {e}")
    
    def _disconnect_chat_server(self):
        """Odpoj sa od servera."""
        self.chat_client = None
        self.chat_messages = []
        
        self._set_chat_status("disconnected", "Odpojené")
        self.chat_connect_btn.setEnabled(True)
        self.chat_disconnect_btn.setEnabled(False)
        self.chat_input.setEnabled(False)
        self.chat_send_btn.setEnabled(False)
        
        self._append_chat_message("System", "🔴 Odpojené od servera", "assistant")
        log.info("Disconnected from agent chat")
    
    def _send_chat_message(self):
        """Odošli user správu a spusti agent loop."""
        user_input = self.chat_input.text().strip()
        if not user_input:
            return
        
        if not self.chat_client:
            QMessageBox.warning(self, "Agent Chat", "Najprv sa pripojte k serveru!")
            return
        
        # Show user message
        self._append_chat_message("User", user_input, "user")
        self.chat_input.clear()
        self.chat_input.setEnabled(False)
        self.chat_send_btn.setEnabled(False)
        
        # Show loading animation
        self._show_loading_animation()
        
        # Add to message history
        self.chat_messages.append({
            "role": "user",
            "content": user_input
        })
        
        # Create and start agent worker
        worker = AgentChatWorker(
            self.chat_client,
            self.chat_messages.copy(),
            self.chat_available_functions,
            auto_execute=self.chat_auto_execute.isChecked()
        )
        
        worker.message_received.connect(self._on_agent_message)
        worker.tool_call_started.connect(self._on_tool_call_started)
        worker.tool_call_finished.connect(self._on_tool_call_finished)
        worker.error_occurred.connect(self._on_agent_error)
        worker.status_update.connect(self._set_chat_status_text)
        
        worker.finished.connect(lambda: self._on_agent_finished(worker))
        worker.start()
        
        self.chat_workers.append(worker)
    
    def _on_tool_call_started(self, tool_name: str, args: dict):
        """Handle tool call start."""
        self._append_chat_message("Tool", "", "tool_call", {
            "tool_name": tool_name,
            "args": args
        })
    
    def _on_tool_call_finished(self, tool_name: str, result_data: dict):
        """Handle tool call completion."""
        self._append_chat_message("Tool", "", "tool_result", result_data)
    
    def _on_agent_message(self, content: str, full_message: dict):
        """Handle final agent response."""
        # Show thinking ONLY in reasoning panel (not in chat)
        thinking_content = None
        if "thinking" in full_message and full_message["thinking"]:
            thinking_content = full_message["thinking"]
            self._append_reasoning_detail(thinking_content)
        elif "reasoning" in full_message and full_message["reasoning"]:
            thinking_content = full_message["reasoning"]
            self._append_reasoning_detail(thinking_content)
        
        # Show assistant message (with clickable link to thinking if present)
        if content:
            extra_data = {"thinking": thinking_content} if thinking_content else None
            self._append_chat_message("Assistant", content, "assistant", extra_data)
        
        # Update message history
        # Worker already updated self.chat_messages through the loop
    
    def _on_agent_error(self, error: str):
        """Handle agent error."""
        self._append_chat_message("System", f"❌ Chyba: {error}", "assistant")
        self._set_chat_status("error", f"Chyba: {error}")
        self.chat_input.setEnabled(True)
        self.chat_send_btn.setEnabled(True)
    
    def _on_agent_finished(self, worker: AgentChatWorker):
        """Handle agent worker finish."""
        # Hide loading animation
        self._hide_loading_animation()
        
        # Re-enable input
        self.chat_input.setEnabled(True)
        self.chat_send_btn.setEnabled(True)
        self._set_chat_status("connected", "Pripravené")
        
        # Update message history from worker
        self.chat_messages = worker.messages
        
        # Remove worker from list
        if worker in self.chat_workers:
            self.chat_workers.remove(worker)
    
    def _set_chat_status(self, status: str, text: str):
        """Set chat status indicator."""
        if status == "connected":
            self.chat_status_indicator.setStyleSheet("color: #4caf50; font-size: 16px;")
        elif status == "error":
            self.chat_status_indicator.setStyleSheet("color: #f44336; font-size: 16px;")
        else:
            self.chat_status_indicator.setStyleSheet("color: #666; font-size: 16px;")
        
        self.chat_status_text.setText(text)
        self.chat_status_text.setStyleSheet(
            f"color: {'#4caf50' if status == 'connected' else '#f44336' if status == 'error' else '#666'};"
        )
    
    def _set_chat_status_text(self, text: str):
        """Set just the status text."""
        self.chat_status_text.setText(text)
    
    def _clear_chat_history(self):
        """Vyčisti chat históriu."""
        reply = QMessageBox.question(
            self, "Vyčistiť chat", 
            "Naozaj chcete vyčistiť celú chat históriu?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.chat_display.clear()
            self.chat_display._message_thinking_map.clear()
            self.chat_display._message_positions.clear()
            self.chat_messages = []
            self.chat_request_counter = 0
            self.chat_message_counter.setText("Messages: 0")
            log.info("Chat history cleared")
    
    def _clear_reasoning_detail(self):
        """Vyčisti reasoning detail panel."""
        self.reasoning_detail_display.clear()
    
    def _on_message_clicked(self, msg_id: str):
        """Handle click on a message - show its thinking in reasoning panel s typing efektom."""
        thinking = self.chat_display._message_thinking_map.get(msg_id)
        if thinking:
            # Clear and show the clicked message's thinking
            self.reasoning_detail_display.clear()
            
            # Stop any ongoing animation
            if self.thinking_timer:
                self.thinking_timer.stop()
                self.thinking_timer = None
            
            cursor = self.reasoning_detail_display.textCursor()
            timestamp = datetime.now().strftime("%H:%M:%S")
            
            # Show header
            cursor.insertHtml(
                f'<div style="color: #4caf50; font-weight: bold; margin-bottom: 8px;">'
                f'💭 Thinking Detail - Message {msg_id}</div>'
                f'<div style="color: #666; font-size: 11px; margin-bottom: 12px;">'
                f'Clicked at {timestamp}</div>'
            )
            
            # Start typing animation for clicked message
            self.thinking_text = thinking
            self.thinking_position = 0
            self.thinking_timer = QTimer(self)
            self.thinking_timer.timeout.connect(self._update_thinking_animation)
            self.thinking_timer.start(15)  # Faster for clicked messages (15ms)
            
            self.reasoning_detail_display.setTextCursor(cursor)
            
            log.info(f"Displayed thinking for message {msg_id} with typing effect")
    
    def _show_loading_animation(self):
        """Zobraz loading animáciu v chate - typing dots style ako Claude."""
        cursor = self.chat_display.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        
        # Store position for updates
        self.loading_cursor_position = cursor.position()
        
        # Initial loading message
        cursor.insertHtml(
            '<div style="margin: 12px 0; padding: 14px; '
            'background: #1a1f2f; border-left: 4px solid #64b5f6; border-radius: 6px;">'
            '<span style="color: #64b5f6; font-weight: bold; font-size: 13px;">⚙️ AI premýšľa</span>'
            '<span id="loading_dots" style="color: #64b5f6; font-size: 13px;"></span>'
            '<span style="color: #ffb74d; margin-left: 6px;">✨</span>'
            '</div>'
        )
        
        self.chat_display.setTextCursor(cursor)
        self.chat_display.ensureCursorVisible()
        
        # Start animated dots timer
        self.loading_dots = 0
        self.loading_timer = QTimer(self)
        self.loading_timer.timeout.connect(self._update_loading_animation)
        self.loading_timer.start(400)  # Update every 400ms
    
    def _update_loading_animation(self):
        """Update loading dots animation - progresívne bodky."""
        if self.loading_cursor_position < 0:
            return
        
        # Cycle through ., .., ..., empty
        self.loading_dots = (self.loading_dots + 1) % 4
        dots = "." * self.loading_dots if self.loading_dots > 0 else ""
        
        # Get current text and replace loading section
        cursor = self.chat_display.textCursor()
        cursor.setPosition(self.loading_cursor_position)
        cursor.movePosition(QTextCursor.MoveOperation.End, QTextCursor.MoveMode.KeepAnchor)
        
        # Clear and redraw
        cursor.removeSelectedText()
        cursor.insertHtml(
            '<div style="margin: 12px 0; padding: 14px; '
            'background: #1a1f2f; border-left: 4px solid #64b5f6; border-radius: 6px;">'
            '<span style="color: #64b5f6; font-weight: bold; font-size: 13px;">⚙️ AI premýšľa'
            f'{dots}</span>'
            '<span style="color: #ffb74d; margin-left: 6px;">✨</span>'
            '</div>'
        )
        
        self.chat_display.ensureCursorVisible()
    
    def _hide_loading_animation(self):
        """Zastav a odstráň loading animáciu."""
        if self.loading_timer:
            self.loading_timer.stop()
            self.loading_timer = None
        
        # Remove loading message by deleting from stored position
        if self.loading_cursor_position >= 0:
            cursor = self.chat_display.textCursor()
            cursor.setPosition(self.loading_cursor_position)
            cursor.movePosition(QTextCursor.MoveOperation.End, QTextCursor.MoveMode.KeepAnchor)
            cursor.removeSelectedText()
            self.loading_cursor_position = -1
    
    def closeEvent(self, event):
        """Spracuj zatvorenie okna."""
        # Stop animations
        if self.loading_timer:
            self.loading_timer.stop()
            self.loading_timer = None
        
        if self.thinking_timer:
            self.thinking_timer.stop()
            self.thinking_timer = None
        
        # Zastav všetky worker thready
        for worker in self.workers.values():
            if worker.isRunning():
                worker.quit()
                worker.wait(3000)  # Čakaj max 3 sekundy
        
        # Zastav chat workers
        for worker in self.chat_workers:
            if worker.isRunning():
                worker.stop()
                worker.quit()
                worker.wait(3000)
        
        # Zatvor logs dialog ak je otvorený
        if self.logs_dialog:
            self.logs_dialog.close()
        
        event.accept()
