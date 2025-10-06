"""IQ Test Creator Window.

Allows creating IQ tests by playing as the AI and saving the expected best move.
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QThread, QObject, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QMessageBox, QDialog, QFormLayout, QLineEdit, QTextEdit,
    QDialogButtonBox, QFileDialog,
)

from ..core.board import Board
from ..core.iq_test import create_iq_test, save_iq_test
from ..core.rules import (
    placements_in_line, no_gaps_in_line, first_move_must_cover_center,
    connected_to_existing, extract_all_words,
)
from ..core.scoring import score_words
from ..core.types import Placement, Direction
from ..core.rack import restore_rack
from ..core.variant_store import VariantDefinition
from ..logging_setup import TRACE_ID_VAR
from ..ai.client import OpenAIClient
from .app import BoardView, RackView

log = logging.getLogger("scrabgpt.ui")

TILE_MIME = "application/x-scrabgpt-tile"


class IQTestSaveDialog(QDialog):
    """Dialog for entering IQ test metadata."""
    
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Uložiť IQ test")
        self.resize(500, 300)
        
        layout = QFormLayout(self)
        
        self.name_edit = QLineEdit(self)
        self.name_edit.setPlaceholderText("napr. opening_center_bingo")
        layout.addRow("Názov testu:", self.name_edit)
        
        self.description_edit = QTextEdit(self)
        self.description_edit.setPlaceholderText(
            "Popis testu a očakávaného správania AI...\n"
            "napr. 'AI by mala nájsť bingo cez stred s vysokým skóre'"
        )
        self.description_edit.setMaximumHeight(100)
        layout.addRow("Popis:", self.description_edit)
        
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
    
    def get_name(self) -> str:
        return self.name_edit.text().strip()
    
    def get_description(self) -> str:
        return self.description_edit.toPlainText().strip()


class IQTestCreatorWindow(QDialog):
    """Modal dialog for creating IQ tests by playing as AI."""
    
    def __init__(
        self,
        board: Board,
        ai_rack: list[str],
        variant_definition: VariantDefinition,
        ai_client: OpenAIClient | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Vytvoriť IQ test")
        self.setModal(True)
        self.resize(1000, 800)
        self.setWindowFlags(
            Qt.WindowType.Window |
            Qt.WindowType.WindowTitleHint |
            Qt.WindowType.WindowCloseButtonHint |
            Qt.WindowType.WindowMaximizeButtonHint
        )
        
        from ..core.assets import get_premiums_path
        self.original_board = board
        self.board = Board(get_premiums_path())
        for r in range(15):
            for c in range(15):
                self.board.cells[r][c].letter = board.cells[r][c].letter
                self.board.cells[r][c].is_blank = board.cells[r][c].is_blank
                self.board.cells[r][c].premium_used = board.cells[r][c].premium_used
        
        self.ai_rack = ai_rack.copy()
        self.original_rack = ai_rack.copy()
        self.variant_definition = variant_definition
        self.ai_client = ai_client
        
        self.pending: list[Placement] = []
        self._pending_words_coords: list[tuple[str, list[tuple[int, int]]]] = []
        self._is_board_empty_at_start = not any(
            board.cells[r][c].letter for r in range(15) for c in range(15)
        )
        
        self._judge_thread: QThread | None = None
        self._last_validated_score: int = 0
        self._last_validated_word: str = ""
        self._last_validated_direction: str = ""
        self._move_is_valid = False
        
        self._setup_ui()
    
    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)
        
        header = QWidget()
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        
        title = QLabel("🧠 Vytvorenie IQ testu")
        title.setStyleSheet(
            "font-size: 18px; font-weight: bold; padding: 8px; "
            "color: #2c3e50; background: #ecf0f1; border-radius: 6px;"
        )
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(title)
        
        info = QLabel(
            "<b>Hraj ako AI:</b> Polož písmená z racku na dosku. "
            "Klikni <b>Validovať ťah</b> (overí pravidlá + slová), "
            "potom <b>Uložiť ako IQ test</b>."
        )
        info.setWordWrap(True)
        info.setStyleSheet(
            "padding: 10px; background: #e8f5e9; border-radius: 6px; "
            "border-left: 4px solid #4caf50; font-size: 13px;"
        )
        header_layout.addWidget(info)
        
        layout.addWidget(header)
        
        board_container = QWidget()
        board_container.setStyleSheet(
            "background-color: #000000; border-radius: 8px; padding: 10px;"
        )
        board_layout = QVBoxLayout(board_container)
        board_layout.setContentsMargins(10, 10, 10, 10)
        
        board_label = QLabel("Herná doska")
        board_label.setStyleSheet("color: white; font-weight: bold; font-size: 14px;")
        board_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        board_layout.addWidget(board_label)
        
        self.board_view = BoardView(self.board)
        self.board_view.cellClicked.connect(self._on_board_clicked)
        self.board_view.set_tile_drop_handler(self._handle_tile_drop)
        self.board_view.set_pending_drag_handler(self._handle_pending_drag_finished)
        board_layout.addWidget(self.board_view)
        
        layout.addWidget(board_container, stretch=1)
        
        rack_container = QWidget()
        rack_container.setStyleSheet(
            "background-color: #1a1a1a; border-radius: 8px; padding: 8px;"
        )
        rack_layout = QVBoxLayout(rack_container)
        rack_layout.setContentsMargins(8, 8, 8, 8)
        rack_layout.setSpacing(5)
        
        rack_label = QLabel("AI Rack (pretiahni písmená na dosku)")
        rack_label.setStyleSheet("color: white; font-weight: bold; font-size: 13px;")
        rack_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        rack_layout.addWidget(rack_label)
        
        self.rack = RackView()
        self.rack.set_letters(self.ai_rack)
        rack_layout.addWidget(self.rack)
        
        layout.addWidget(rack_container)
        
        self.status_label = QLabel("")
        self.status_label.setStyleSheet(
            "padding: 8px; background: #ecf0f1; border-radius: 4px; "
            "font-size: 13px; min-height: 20px;"
        )
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)
        
        button_panel = QWidget()
        button_panel.setStyleSheet(
            "background-color: #ecf0f1; border-radius: 8px; padding: 10px;"
        )
        button_layout = QHBoxLayout(button_panel)
        button_layout.setSpacing(10)
        
        self.clear_btn = QPushButton("🗑️ Vymazať rozloženie")
        self.clear_btn.clicked.connect(self._clear_pending)
        self.clear_btn.setStyleSheet(
            "QPushButton { "
            "background-color: #95a5a6; color: white; font-weight: bold; "
            "padding: 10px 15px; border-radius: 6px; font-size: 13px; "
            "} "
            "QPushButton:hover { background-color: #7f8c8d; } "
            "QPushButton:pressed { background-color: #6c7a7b; }"
        )
        button_layout.addWidget(self.clear_btn)
        
        button_layout.addStretch()
        
        self.validate_btn = QPushButton("✓ Validovať ťah")
        self.validate_btn.clicked.connect(self._validate_and_judge)
        self.validate_btn.setStyleSheet(
            "QPushButton { "
            "background-color: #2196f3; color: white; font-weight: bold; "
            "padding: 10px 20px; border-radius: 6px; font-size: 14px; "
            "} "
            "QPushButton:hover { background-color: #1976d2; } "
            "QPushButton:pressed { background-color: #1565c0; } "
            "QPushButton:disabled { background-color: #bdbdbd; }"
        )
        button_layout.addWidget(self.validate_btn)
        
        self.save_btn = QPushButton("💾 Uložiť ako IQ test")
        self.save_btn.clicked.connect(self._save_iq_test)
        self.save_btn.setEnabled(False)
        self.save_btn.setStyleSheet(
            "QPushButton { "
            "background-color: #4caf50; color: white; font-weight: bold; "
            "padding: 10px 20px; border-radius: 6px; font-size: 14px; "
            "} "
            "QPushButton:hover { background-color: #45a049; } "
            "QPushButton:pressed { background-color: #3d8b40; } "
            "QPushButton:disabled { background-color: #bdbdbd; }"
        )
        button_layout.addWidget(self.save_btn)
        
        layout.addWidget(button_panel)
    
    def _on_board_clicked(self, row: int, col: int) -> None:
        if self.board.cells[row][col].letter:
            return
        
        selected_tile = self.rack.take_selected()
        if selected_tile is None:
            return
        
        blank_as: str | None = None
        if selected_tile == "?":
            from PySide6.QtWidgets import QInputDialog
            text, ok = QInputDialog.getText(
                self,
                "Blank",
                f"Zadaj písmeno pre blank na [{row},{col}]:",
            )
            if not ok or not text:
                self.ai_rack.append(selected_tile)
                self.rack.set_letters(self.ai_rack)
                return
            blank_as = text.strip().upper()
            if not blank_as or len(blank_as) != 1:
                QMessageBox.warning(self, "Blank", "Zadaj jedno písmeno.")
                self.ai_rack.append(selected_tile)
                self.rack.set_letters(self.ai_rack)
                return
        
        placement = Placement(row=row, col=col, letter=selected_tile, blank_as=blank_as)
        self.pending.append(placement)
        self.board_view.set_pending(self.pending)
        self._move_is_valid = False
        self.save_btn.setEnabled(False)
        self.status_label.setText(
            f"✓ Položené: {len(self.pending)} písmen. Klikni 'Validovať ťah' pre overenie."
        )
        self.status_label.setStyleSheet(
            "padding: 8px; background: #fff3cd; border-radius: 4px; "
            "font-size: 13px; min-height: 20px; color: #856404;"
        )
    
    def _clear_pending(self) -> None:
        self.ai_rack = restore_rack(self.ai_rack, self.pending)
        self.pending = []
        self.rack.set_letters(self.ai_rack)
        self.board_view.set_pending(self.pending)
        self._move_is_valid = False
        self.save_btn.setEnabled(False)
        self.status_label.setText("Rozloženie vymazané. Začni odznova.")
        self.status_label.setStyleSheet(
            "padding: 8px; background: #ecf0f1; border-radius: 4px; "
            "font-size: 13px; min-height: 20px;"
        )
    
    def _handle_tile_drop(self, row: int, col: int, payload: dict[str, Any]) -> bool:
        if self.board.cells[row][col].letter:
            return False
        
        origin = payload.get("origin")
        if origin == "board":
            old_row = payload.get("row")
            old_col = payload.get("col")
            if old_row is None or old_col is None:
                return False
            
            for i, p in enumerate(self.pending):
                if p.row == old_row and p.col == old_col:
                    self.pending[i] = Placement(
                        row=row, col=col, letter=p.letter, blank_as=p.blank_as
                    )
                    self.board_view.set_pending(self.pending)
                    self._move_is_valid = False
                    self.save_btn.setEnabled(False)
                    return True
            return False
        
        elif origin == "rack":
            letter = payload.get("letter")
            if not isinstance(letter, str):
                return False
            
            if letter not in self.ai_rack:
                return False
            
            blank_as: str | None = None
            if letter == "?":
                from PySide6.QtWidgets import QInputDialog
                text, ok = QInputDialog.getText(
                    self,
                    "Blank",
                    f"Zadaj písmeno pre blank na [{row},{col}]:",
                )
                if not ok or not text:
                    return False
                blank_as = text.strip().upper()
                if not blank_as or len(blank_as) != 1:
                    QMessageBox.warning(self, "Blank", "Zadaj jedno písmeno.")
                    return False
            
            self.ai_rack.remove(letter)
            placement = Placement(row=row, col=col, letter=letter, blank_as=blank_as)
            self.pending.append(placement)
            self.rack.set_letters(self.ai_rack)
            self.board_view.set_pending(self.pending)
            self._move_is_valid = False
            self.save_btn.setEnabled(False)
            self.status_label.setText(
                f"✓ Položené: {len(self.pending)} písmen. Klikni 'Validovať ťah'."
            )
            self.status_label.setStyleSheet(
                "padding: 8px; background: #fff3cd; border-radius: 4px; "
                "font-size: 13px; min-height: 20px; color: #856404;"
            )
            return True
        
        return False
    
    def _handle_pending_drag_finished(
        self, payload: dict[str, Any], action: Qt.DropAction
    ) -> None:
        if action != Qt.DropAction.MoveAction:
            return
        
        origin = payload.get("origin")
        if origin != "board":
            return
        
        old_row = payload.get("row")
        old_col = payload.get("col")
        if old_row is None or old_col is None:
            return
        
        for i, p in enumerate(self.pending):
            if p.row == old_row and p.col == old_col:
                del self.pending[i]
                self.ai_rack.append(p.letter)
                self.rack.set_letters(self.ai_rack)
                self.board_view.set_pending(self.pending)
                self._move_is_valid = False
                self.save_btn.setEnabled(False)
                self.status_label.setText(
                    f"✓ Položené: {len(self.pending)} písmen. Klikni 'Validovať ťah'."
                )
                self.status_label.setStyleSheet(
                    "padding: 8px; background: #fff3cd; border-radius: 4px; "
                    "font-size: 13px; min-height: 20px; color: #856404;"
                )
                return
    
    def _validate_and_judge(self) -> None:
        if not self.pending:
            QMessageBox.warning(self, "Validácia", "Najprv polož aspoň jedno písmeno.")
            return
        
        dir_ = placements_in_line(self.pending)
        if dir_ is None:
            QMessageBox.warning(self, "Validácia", "Písmená musia byť v jednej línii.")
            return
        
        if not no_gaps_in_line(self.board, self.pending, dir_):
            QMessageBox.warning(self, "Validácia", "V hlavnej línii sú diery.")
            return
        
        if self._is_board_empty_at_start:
            if not first_move_must_cover_center(self.pending):
                QMessageBox.warning(
                    self, "Validácia", "Prvý ťah musí prechádzať stredom (★)."
                )
                return
        else:
            if not connected_to_existing(self.board, self.pending):
                QMessageBox.warning(
                    self, "Validácia", "Ťah musí nadväzovať na existujúce písmená."
                )
                return
        
        self.board.place_letters(self.pending)
        words_found = extract_all_words(self.board, self.pending)
        self.board.clear_letters(self.pending)
        
        if not words_found:
            QMessageBox.warning(self, "Validácia", "Žiadne slová neboli vytvorené.")
            return
        
        words_coords = [(wf.word, wf.letters) for wf in words_found]
        words = [wf.word for wf in words_found]
        self._pending_words_coords = words_coords
        self._last_validated_direction = "ACROSS" if dir_ == Direction.ACROSS else "DOWN"
        
        score, _ = score_words(self.board, self.pending, words_coords)
        if len(self.original_rack) == len(self.pending):
            score += 50
        self._last_validated_score = score
        self._last_validated_word = words[0] if words else ""
        
        self.status_label.setText(f"⏳ Overujem slová: {', '.join(words)}...")
        self.status_label.setStyleSheet(
            "padding: 8px; background: #cce5ff; border-radius: 4px; "
            "font-size: 13px; min-height: 20px; color: #004085;"
        )
        self.validate_btn.setEnabled(False)
        
        if self.ai_client is None:
            self.ai_client = OpenAIClient()
        
        class JudgeWorker(QObject):
            finished: Signal = Signal(dict)
            failed: Signal = Signal(Exception)
            
            def __init__(
                self, client: OpenAIClient, words: list[str], language: str
            ) -> None:
                super().__init__()
                self.client = client
                self.words = words
                self.language = language
            
            def run(self) -> None:
                try:
                    TRACE_ID_VAR.set(str(uuid.uuid4())[:8])
                    resp = self.client.judge_words(self.words, language=self.language)
                    self.finished.emit(resp)
                except Exception as e:
                    self.failed.emit(e)
        
        self._judge_thread = QThread(self)
        worker = JudgeWorker(self.ai_client, words, self.variant_definition.language)
        worker.moveToThread(self._judge_thread)
        
        self._judge_thread.started.connect(worker.run)
        worker.finished.connect(self._on_judge_finished)
        worker.failed.connect(self._on_judge_failed)
        worker.finished.connect(self._judge_thread.quit)
        worker.failed.connect(self._judge_thread.quit)
        
        self._judge_thread.start()
    
    def _on_judge_finished(self, response: dict[str, Any]) -> None:
        self.validate_btn.setEnabled(True)
        
        all_valid = response.get("all_valid", False)
        if not all_valid:
            results = response.get("results", [])
            invalid_words = [
                f"{r['word']}: {r.get('reason', 'neplatné')}"
                for r in results
                if not r.get("valid", False)
            ]
            msg = "Niektoré slová sú neplatné:\n" + "\n".join(invalid_words)
            QMessageBox.warning(self, "Neplatný ťah", msg)
            self.status_label.setText("✗ Ťah je neplatný - oprav a skús znova.")
            self.status_label.setStyleSheet(
                "padding: 8px; background: #f8d7da; border-radius: 4px; "
                "font-size: 13px; min-height: 20px; color: #721c24;"
            )
            self._move_is_valid = False
            self.save_btn.setEnabled(False)
            return
        
        self._move_is_valid = True
        self.save_btn.setEnabled(True)
        self.status_label.setText(
            f"✓ Ťah je platný! Skóre: {self._last_validated_score} bodov. "
            f"Teraz môžeš uložiť IQ test."
        )
        self.status_label.setStyleSheet(
            "padding: 8px; background: #d4edda; border-radius: 4px; "
            "font-size: 13px; min-height: 20px; color: #155724; font-weight: bold;"
        )
        QMessageBox.information(
            self,
            "Validácia úspešná",
            f"Všetky slová sú platné.\nSkóre: {self._last_validated_score} bodov",
        )
    
    def _on_judge_failed(self, error: Exception) -> None:
        self.validate_btn.setEnabled(True)
        QMessageBox.critical(
            self,
            "Chyba rozhodcu",
            f"Validácia zlyhala:\n{error}",
        )
        self.status_label.setText(f"✗ Validácia zlyhala: {str(error)[:100]}")
        self.status_label.setStyleSheet(
            "padding: 8px; background: #f8d7da; border-radius: 4px; "
            "font-size: 13px; min-height: 20px; color: #721c24;"
        )
    
    def _save_iq_test(self) -> None:
        if not self._move_is_valid:
            QMessageBox.warning(
                self, "Uloženie", "Najprv validuj ťah pomocou 'Validovať ťah'."
            )
            return
        
        dialog = IQTestSaveDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        
        name = dialog.get_name()
        description = dialog.get_description()
        
        if not name:
            QMessageBox.warning(self, "Uloženie", "Zadaj názov testu.")
            return
        
        filename = name.replace(" ", "_") + ".iq"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Uložiť IQ test",
            str(Path.cwd() / "tests" / "iq_tests" / filename),
            "IQ Test Files (*.iq)",
        )
        
        if not path:
            return
        
        blanks_map: dict[tuple[int, int], str] | None = None
        for p in self.pending:
            if p.letter == "?" and p.blank_as:
                if blanks_map is None:
                    blanks_map = {}
                blanks_map[(p.row, p.col)] = p.blank_as
        
        test = create_iq_test(
            name=name,
            description=description,
            board=self.original_board,
            ai_rack=self.original_rack,
            expected_placements=self.pending,
            expected_direction=self._last_validated_direction,
            expected_word=self._last_validated_word,
            expected_score=self._last_validated_score,
            expected_blanks=blanks_map,
            variant_slug=self.variant_definition.slug,
        )
        
        try:
            save_iq_test(test, Path(path))
            QMessageBox.information(
                self,
                "Uložené",
                f"IQ test bol uložený do:\n{path}",
            )
            self.close()
        except Exception as e:
            QMessageBox.critical(
                self,
                "Chyba",
                f"Nepodarilo sa uložiť test:\n{e}",
            )
