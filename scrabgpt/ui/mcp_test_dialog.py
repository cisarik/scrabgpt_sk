"""MCP Test Dialog - UI pre testovanie MCP serverov a nástrojov."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QFont, QTextCursor, QMouseEvent
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QTabWidget, 
    QWidget, QTextEdit, QComboBox, QLineEdit, QFormLayout, QGroupBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QSplitter, QFrame,
    QMessageBox, QFileDialog, QCheckBox, QSpinBox, QScrollArea, QInputDialog
)

from ..ai.mcp_tools import get_all_tool_names, get_tool_function

log = logging.getLogger("scrabgpt.ui.mcp_test")


class ClickableLabel(QLabel):
    """Label that emits clicked signal when clicked."""
    
    clicked = Signal()
    
    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Handle mouse press event."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


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
    
    def closeEvent(self, event):
        """Spracuj zatvorenie okna."""
        # Zastav všetky worker thready
        for worker in self.workers.values():
            if worker.isRunning():
                worker.quit()
                worker.wait(3000)  # Čakaj max 3 sekundy
        
        # Zatvor logs dialog ak je otvorený
        if self.logs_dialog:
            self.logs_dialog.close()
        
        event.accept()
