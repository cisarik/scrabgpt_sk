from __future__ import annotations
import os
import sys
import uuid
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal, Optional, Sequence, cast
from pathlib import Path
from PySide6.QtCore import Qt, QSize, QRectF, QTimer, Signal, QObject, QThread, QPoint, QMimeData
from PySide6.QtGui import QAction, QPainter, QColor, QPen, QFont, QMouseEvent, QPaintEvent, QIntValidator, QTextCursor, QPixmap, QDrag
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QToolBar, QLabel, QSplitter, QStatusBar, QMessageBox, QPushButton,
    QDialog, QFormLayout, QLineEdit, QDialogButtonBox, QListWidget, QListWidgetItem,
    QGridLayout, QGraphicsDropShadowEffect, QListView, QPlainTextEdit, QCheckBox,
    QComboBox
)
from ..logging_setup import configure_logging, TRACE_ID_VAR, default_log_path

from ..core.board import Board
from ..core.assets import get_premiums_path
from ..core.tiles import TileBag
from ..core.game import (
    GameEndReason,
    PlayerState,
    apply_final_scoring,
    determine_end_reason,
)
from ..core.rules import placements_in_line  # noqa: F401 (placeholder, will be used in next slices)
from ..core.rules import first_move_must_cover_center, connected_to_existing, no_gaps_in_line, extract_all_words
from ..core.scoring import score_words, apply_premium_consumption
from ..core.types import Placement, Premium
from ..ai.client import OpenAIClient, TokenBudgetExceededError
from ..ai.player import propose_move as ai_propose_move
from ..ai.player import should_auto_trigger_ai_opening, is_board_empty
from ..core.state import build_ai_state_dict
from ..core.rack import consume_rack
from ..core.state import build_save_state_dict, parse_save_state_dict, restore_board_from_save, restore_bag_from_save
from ..core.variant_store import (
    VariantDefinition,
    get_active_variant_slug,
    list_installed_variants,
    load_variant,
    set_active_variant_slug,
)
from ..ai.variants import (
    LanguageInfo,
    download_and_store_variant,
    fetch_supported_languages,
    get_languages_for_ui,
    match_language,
)

ASSETS = str(Path(__file__).parent / ".." / "assets")
PREMIUMS_PATH = get_premiums_path()
ROOT_DIR = Path(__file__).resolve().parents[2]
ENV_PATH = str(ROOT_DIR / ".env")
LOG_PATH = default_log_path()
EUR_PER_TOKEN = 0.00000186  # 1 token ≈ 0.00000186 EUR (zadané majiteľom)

TILE_MIME = "application/x-scrabgpt-tile"

# Typ alias pre strany pri určovaní štartéra
StarterSide = Literal["HUMAN", "AI"]

@dataclass(frozen=True)
class _SpinnerEntry:
    owner: str
    base_text: str
    wait_cursor: bool

# ---------- Logging + trace_id ----------
# Použi centralizovanú konfiguráciu (zabráni duplicitám handlerov)
log = configure_logging()

# ---------- Jednoduché UI prvky ----------

class NewVariantDialog(QDialog):
    """Dialog na zadanie parametrov pre stiahnutie nového Scrabble variantu."""

    def __init__(
        self,
        parent: QWidget | None,
        languages: Sequence[LanguageInfo],
        default_language: LanguageInfo | None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Nový variant Scrabble")

        layout = QFormLayout(self)

        self.language_combo = QComboBox(self)
        self._languages: list[LanguageInfo] = list(languages)
        for lang in self._languages:
            self.language_combo.addItem(lang.display_label(), lang)
        if default_language:
            for idx, lang in enumerate(self._languages):
                if lang.name == default_language.name and lang.code == default_language.code:
                    self.language_combo.setCurrentIndex(idx)
                    break

        self.query_edit = QLineEdit(self)
        if default_language:
            self.query_edit.setText(default_language.name)
        self.query_edit.setPlaceholderText("Napr. Slovenský Scrabble variant")

        layout.addRow("Jazyk:", self.language_combo)
        layout.addRow("Popis variantu:", self.query_edit)

        info = QLabel(
            "Zadaný text sa vloží do promptu pre OpenAI. Pridaj jazyk aj prípadné "
            "špecifiká (napr. regionálnu verziu)."
        )
        info.setWordWrap(True)
        layout.addRow(info)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def selected_language(self) -> LanguageInfo | None:
        data = self.language_combo.currentData()
        return data if isinstance(data, LanguageInfo) else None

    def query_text(self) -> str:
        text = self.query_edit.text().strip()
        if text:
            return text
        lang = self.selected_language()
        return lang.name if lang else ""


class SettingsDialog(QDialog):
    """Nastavenia - OpenAI API kľúč a limity výstupných tokenov.

    - Umožňuje zadať `AI_MOVE_MAX_OUTPUT_TOKENS` a `JUDGE_MAX_OUTPUT_TOKENS`.
    - Vpravo priebežne prepočítava odhad ceny v EUR podľa zadaného počtu tokenov.
    - Uloží hodnoty do `.env` v koreňovom adresári projektu a do `os.environ`.
    """
    def __init__(self, parent: QWidget | None = None, *, repro_mode: bool = False, repro_seed: int = 0) -> None:
        super().__init__(parent)
        self.setWindowTitle("Nastavenia")
        self.selected_variant_slug = get_active_variant_slug()
        self._installed_variants: list[VariantDefinition] = []
        self._languages: list[LanguageInfo] = []

        lay = QFormLayout(self)
        # Načítaj .env, aby sa predvyplnil API key (ak existuje)
        try:
            from dotenv import load_dotenv as _load_dotenv  # lokálny import
            _load_dotenv(ENV_PATH, override=False)
        except Exception:
            pass

        self.key_edit = QLineEdit(self)
        self.key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_edit.setText(os.getenv("OPENAI_API_KEY", ""))
        lay.addRow("OpenAI API key:", self.key_edit)

        # --- Limity výstupných tokenov ---
        self.ai_tokens_edit = QLineEdit(self)
        self.ai_tokens_edit.setValidator(QIntValidator(1, 1_000_000, self))
        self.ai_tokens_edit.setText(os.getenv("AI_MOVE_MAX_OUTPUT_TOKENS", "3600"))
        self.ai_tokens_cost = QLabel("")
        self.ai_tokens_cost.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        ai_row = QHBoxLayout()
        ai_row.addWidget(self.ai_tokens_edit, 2)
        ai_row.addWidget(self.ai_tokens_cost, 1)
        ai_row_w = QWidget(self)
        ai_row_w.setLayout(ai_row)
        lay.addRow("AI ťah — max výstupných tokenov:", ai_row_w)

        self.judge_tokens_edit = QLineEdit(self)
        self.judge_tokens_edit.setValidator(QIntValidator(1, 1_000_000, self))
        self.judge_tokens_edit.setText(os.getenv("JUDGE_MAX_OUTPUT_TOKENS", "800"))
        self.judge_tokens_cost = QLabel("")
        self.judge_tokens_cost.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        j_row = QHBoxLayout()
        j_row.addWidget(self.judge_tokens_edit, 2)
        j_row.addWidget(self.judge_tokens_cost, 1)
        j_row_w = QWidget(self)
        j_row_w.setLayout(j_row)
        lay.addRow("Rozhodca — max výstupných tokenov:", j_row_w)

        # --- Výber variantov ---
        self.variant_combo = QComboBox(self)
        self.variant_combo.setEditable(False)
        self.variant_combo.currentIndexChanged.connect(self._on_variant_changed)
        lay.addRow("Aktívny Scrabble variant:", self.variant_combo)

        self.languages_combo = QComboBox(self)
        self.languages_combo.setEditable(False)
        lang_row = QHBoxLayout()
        lang_row.addWidget(self.languages_combo, 2)
        self.refresh_languages_btn = QPushButton("Aktualizovať jazyky", self)
        self.refresh_languages_btn.clicked.connect(self._refresh_languages)
        lang_row.addWidget(self.refresh_languages_btn)
        self.new_variant_btn = QPushButton("Nový variant", self)
        self.new_variant_btn.clicked.connect(self._on_new_variant)
        lang_row.addWidget(self.new_variant_btn)
        lang_container = QWidget(self)
        lang_container.setLayout(lang_row)
        lay.addRow("Jazyky OpenAI:", lang_container)

        # --- Repro mód (deterministický seed pre TileBag) ---
        self.repro_check = QCheckBox("Repro mód")
        self.repro_check.setChecked(repro_mode)
        lay.addRow(self.repro_check)

        self.seed_edit = QLineEdit(self)
        self.seed_edit.setValidator(QIntValidator(0, 2_147_483_647, self))
        self.seed_edit.setText(str(repro_seed))
        lay.addRow("Seed:", self.seed_edit)

        # Live prepočet EUR pri zmene
        self.ai_tokens_edit.textChanged.connect(self._update_costs)
        self.judge_tokens_edit.textChanged.connect(self._update_costs)
        self._update_costs()

        self.test_btn = QPushButton("Testovať pripojenie")
        self.test_btn.clicked.connect(self.test_connection)
        lay.addWidget(self.test_btn)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

        self._load_installed_variants(select_slug=self.selected_variant_slug)
        self._init_languages()

    def _update_costs(self) -> None:
        """Prepočet odhadovanej ceny v EUR pre zadaný počet tokenov."""
        def fmt(tokens_text: str) -> str:
            try:
                t = int(tokens_text)
                if t <= 0:
                    return ""
                eur = t * EUR_PER_TOKEN
                # jednoduché formátovanie so 6 des. miestami pre malé čiastky
                if eur < 0.01:
                    return f"≈ {eur:.6f} €"
                return f"≈ {eur:.2f} €"
            except ValueError:
                return ""

        self.ai_tokens_cost.setText(fmt(self.ai_tokens_edit.text()))
        self.judge_tokens_cost.setText(fmt(self.judge_tokens_edit.text()))

    def _load_installed_variants(self, *, select_slug: str | None = None) -> None:
        variants = sorted(list_installed_variants(), key=lambda v: v.language.lower())
        self._installed_variants = variants
        slug_to_select = select_slug or self.selected_variant_slug

        self.variant_combo.blockSignals(True)
        self.variant_combo.clear()
        for variant in variants:
            label = f"{variant.language} ({variant.slug})"
            self.variant_combo.addItem(label, variant.slug)
        self.variant_combo.blockSignals(False)

        if slug_to_select:
            idx = self.variant_combo.findData(slug_to_select)
            if idx >= 0:
                self.variant_combo.setCurrentIndex(idx)
        if self.variant_combo.count() and self.variant_combo.currentIndex() < 0:
            self.variant_combo.setCurrentIndex(0)

        data = self.variant_combo.currentData()
        if isinstance(data, str):
            self.selected_variant_slug = data
        self._sync_language_with_variant(self.selected_variant_slug)

    def _init_languages(self) -> None:
        languages = get_languages_for_ui()
        self._set_languages(languages)
        self._sync_language_with_variant(self.selected_variant_slug)

    def _set_languages(self, languages: Sequence[LanguageInfo], *, keep_selection: bool = False) -> None:
        previous = self._current_language() if keep_selection else None
        self._languages = list(languages)
        self.languages_combo.blockSignals(True)
        self.languages_combo.clear()
        for lang in self._languages:
            self.languages_combo.addItem(lang.display_label(), lang)
        self.languages_combo.blockSignals(False)
        if previous:
            idx = self._index_for_language(previous)
            if idx >= 0:
                self.languages_combo.setCurrentIndex(idx)
                return
        if self.languages_combo.count():
            self.languages_combo.setCurrentIndex(0)

    def _current_language(self) -> LanguageInfo | None:
        data = self.languages_combo.currentData()
        return data if isinstance(data, LanguageInfo) else None

    def _index_for_language(self, language: LanguageInfo) -> int:
        for idx in range(self.languages_combo.count()):
            data = self.languages_combo.itemData(idx)
            if not isinstance(data, LanguageInfo):
                continue
            if data.name.casefold() == language.name.casefold():
                code_a = (data.code or "").casefold()
                code_b = (language.code or "").casefold()
                if code_a == code_b or not code_b:
                    return idx
        return -1

    def _on_variant_changed(self, index: int) -> None:
        data = self.variant_combo.itemData(index)
        if isinstance(data, str):
            self.selected_variant_slug = data
            self._sync_language_with_variant(data)

    def _sync_language_with_variant(self, slug: str | None) -> None:
        if not slug:
            return
        try:
            variant = load_variant(slug)
        except Exception:
            return
        match = match_language(variant.language, self._languages)
        if match:
            idx = self._index_for_language(match)
            if idx >= 0:
                self.languages_combo.setCurrentIndex(idx)
                return
        new_lang = LanguageInfo(name=variant.language, code=None)
        self._languages.append(new_lang)
        self.languages_combo.addItem(new_lang.display_label(), new_lang)
        self.languages_combo.setCurrentIndex(self.languages_combo.count() - 1)

    def _refresh_languages(self) -> None:
        try:
            client = OpenAIClient()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "OpenAI", f"Inicializácia klienta zlyhala: {exc}")
            return
        try:
            languages = fetch_supported_languages(client)
        except Exception as exc:  # noqa: BLE001
            log.exception("refresh_languages_failed", exc_info=exc)
            QMessageBox.critical(self, "OpenAI", f"Zlyhalo načítanie jazykov: {exc}")
            return
        self._set_languages(languages, keep_selection=True)
        self._sync_language_with_variant(self.selected_variant_slug)
        QMessageBox.information(self, "Jazyky", "Zoznam jazykov bol aktualizovaný.")

    def _on_new_variant(self) -> None:
        current_lang = self._current_language()
        dialog = NewVariantDialog(self, self._languages or get_languages_for_ui(), current_lang)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        query = dialog.query_text().strip()
        if not query:
            QMessageBox.warning(self, "Nový variant", "Zadaj jazyk alebo popis variantu.")
            return
        try:
            client = OpenAIClient()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Nový variant", f"OpenAI client sa nepodarilo inicializovať: {exc}")
            return
        language_hint = dialog.selected_language()
        try:
            definition = download_and_store_variant(
                client,
                language_request=query,
                language_hint=language_hint,
            )
        except Exception as exc:  # noqa: BLE001
            log.exception("download_variant_failed", exc_info=exc)
            QMessageBox.critical(self, "Nový variant", f"Získavanie variantu zlyhalo: {exc}")
            return
        self.selected_variant_slug = definition.slug
        # rozšír jazykový zoznam, ak tam ešte nie je
        if not match_language(definition.language, self._languages):
            inferred_code = language_hint.code if language_hint else None
            new_language = LanguageInfo(name=definition.language, code=inferred_code)
            self._languages.append(new_language)
            self.languages_combo.addItem(new_language.display_label(), new_language)
        self._load_installed_variants(select_slug=definition.slug)
        self._sync_language_with_variant(definition.slug)
        QMessageBox.information(
            self,
            "Nový variant",
            f"Variant '{definition.language}' bol uložený (slug {definition.slug}).",
        )

    def test_connection(self) -> None:
        k = self.key_edit.text().strip()
        if not k:
            QMessageBox.warning(self, "Test", "Zadaj API key.")
            return
        os.environ["OPENAI_API_KEY"] = k
        try:
            _ = OpenAIClient()
            # Skus trivialne zavolat judge na bezpecne slovo (bez platenia? real call) - radsej nevolat tu.
            QMessageBox.information(self, "Test", "Kľúč uložený do prostredia. Reálne volanie sa vykoná počas hry.")
        except Exception as e:
            QMessageBox.critical(self, "Test zlyhal", str(e))

    def accept(self) -> None:
        # Ulož do prostredia aj do .env (len ak nezadané prázdne)
        key_str = self.key_edit.text().strip()
        # zaisti existenciu .env v koreňovom adresári
        try:
            if not os.path.exists(ENV_PATH):
                from pathlib import Path as _Path
                _Path(ENV_PATH).open("a", encoding="utf-8").close()
        except Exception:
            # ak sa nepodarí vytvoriť, pokračuj len s os.environ
            pass
        if key_str:
            os.environ["OPENAI_API_KEY"] = key_str
            try:
                from dotenv import set_key as _set_key  # lokálny import, aby UI nemalo tvrdú závislosť na module pri import-time
                _set_key(ENV_PATH, "OPENAI_API_KEY", key_str)
            except Exception:
                # tiché zlyhanie zápisu do .env je akceptovateľné (kľúč ostane v procese)
                pass

        # limity tokenov
        ai_tokens = self.ai_tokens_edit.text().strip() or "3600"
        judge_tokens = self.judge_tokens_edit.text().strip() or "800"
        os.environ["AI_MOVE_MAX_OUTPUT_TOKENS"] = ai_tokens
        os.environ["JUDGE_MAX_OUTPUT_TOKENS"] = judge_tokens
        try:
            from dotenv import set_key as _set_key2
            _set_key2(ENV_PATH, "AI_MOVE_MAX_OUTPUT_TOKENS", ai_tokens)
            _set_key2(ENV_PATH, "JUDGE_MAX_OUTPUT_TOKENS", judge_tokens)
        except Exception:
            pass

        slug_data = self.variant_combo.currentData()
        if isinstance(slug_data, str) and slug_data:
            try:
                variant = set_active_variant_slug(slug_data)
                self.selected_variant_slug = variant.slug
                from dotenv import set_key as _set_key_variant
                _set_key_variant(ENV_PATH, "SCRABBLE_VARIANT", variant.slug)
            except Exception:
                # aj pri zlyhaní zápisu do .env necháme aspoň runtime hodnotu
                os.environ["SCRABBLE_VARIANT"] = slug_data
        super().accept()
        super().accept()


class LogViewerDialog(QDialog):
    """Jednoduchý prehliadač logu s hľadaním.

    Zobrazí posledných N riadkov zo `scrabgpt.log`. Text je len na čítanie.
    """
    def __init__(self, parent: QWidget | None = None, max_lines: int = 500) -> None:
        super().__init__(parent)
        self.setWindowTitle("Log — posledné záznamy")
        self.resize(900, 600)
        lay = QVBoxLayout(self)
        # vyhľadávanie
        search_row = QHBoxLayout()
        self.search_edit = QLineEdit(self)
        self.search_edit.setPlaceholderText("Hľadať…")
        self.search_edit.returnPressed.connect(self._find_next)
        self.find_btn = QPushButton("Hľadať")
        self.find_btn.clicked.connect(self._find_next)
        search_row.addWidget(self.search_edit)
        search_row.addWidget(self.find_btn)
        search_w = QWidget(self)
        search_w.setLayout(search_row)
        lay.addWidget(search_w)

        self.text = QPlainTextEdit(self)
        self.text.setReadOnly(True)
        lay.addWidget(self.text)

        # načítaj obsah
        self._load_tail(LOG_PATH, max_lines)

        close_btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close_btns.rejected.connect(self.reject)
        close_btns.accepted.connect(self.accept)
        lay.addWidget(close_btns)

        self._last_find_pos: int = 0

    def _load_tail(self, path: str, max_lines: int) -> None:
        try:
            from pathlib import Path as _Path
            with _Path(path).open(encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
            tail = "".join(lines[-max_lines:])
        except Exception:
            tail = "(Žiadne logy alebo súbor neexistuje.)"
        self.text.setPlainText(tail)
        # scroll na koniec
        # posun kurzor na koniec dokumentu
        try:
            self.text.moveCursor(QTextCursor.MoveOperation.End)
        except Exception:
            # kompatibilita, ak by sa API lisilo
            cursor = self.text.textCursor()
            self.text.setTextCursor(cursor)

    def _find_next(self) -> None:
        term = self.search_edit.text().strip()
        if not term:
            return
        doc = self.text.document()
        # vyhľadávanie od poslednej pozície
        pos = self._last_find_pos
        found = doc.find(term, pos)
        if not found.isNull():
            self.text.setTextCursor(found)
            self._last_find_pos = found.position()
        else:
            # od začiatku
            found2 = doc.find(term, 0)
            if not found2.isNull():
                self.text.setTextCursor(found2)
                self._last_find_pos = found2.position()

class BoardView(QWidget):
    """Vykreslovanie 15x15 dosky s premiami, pismenami a klik interakciou."""
    cellClicked: Signal = Signal(int, int)  # noqa: N815

    def __init__(self, board: Board, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.board = board
        self.setMinimumSize(QSize(600, 600))
        self.setAcceptDrops(True)
        self._pending: list[Placement] = []
        # posledne potvrdene bunky pre jemne zvyraznenie pocas nasledujuceho tahu
        self._last_move_cells: list[tuple[int, int]] = []
        self._anim_cell: Optional[tuple[int, int]] = None
        self._anim_phase: float = 0.0
        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(16)  # ~60 FPS
        self._anim_timer.timeout.connect(self._on_anim_tick)
        self._drop_handler: Optional[Callable[[int, int, dict[str, Any]], bool]] = None
        self._pending_drag_handler: Optional[Callable[[dict[str, Any], Qt.DropAction], None]] = None
        self._drag_candidate: Optional[Placement] = None
        self._drag_start_pos: Optional[QPoint] = None

    def set_pending(self, placements: list[Placement]) -> None:
        """Nastavi docasne polozene pismena na prekreslenie."""
        self._pending = placements
        self.update()

    def flash_cell(self, row: int, col: int) -> None:
        """Spusti kratku animaciu zvyraznenia bunky pri polozenej kocke."""
        self._anim_cell = (row, col)
        self._anim_phase = 0.0
        self._anim_timer.start()

    def set_last_move_cells(self, cells: list[tuple[int, int]]) -> None:
        """Nastavi bunky posledneho tahu na trvale zvyraznenie do dalsieho tahu."""
        self._last_move_cells = cells
        self.update()

    def _on_anim_tick(self) -> None:
        self._anim_phase += 0.08
        if self._anim_phase >= 1.0:
            self._anim_timer.stop()
        self.update()

    def _grid_geometry(self) -> tuple[float, float, float]:
        """Vypocita lavy horny roh a velkost stvorca bunky pre vycentrovanu mriezku."""
        w = float(self.width())
        h = float(self.height())
        cell = min(w, h) / 15.0
        x0 = (w - 15.0 * cell) / 2.0
        y0 = (h - 15.0 * cell) / 2.0
        return x0, y0, cell

    def paintEvent(self, ev: QPaintEvent) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        x0, y0, cell = self._grid_geometry()

        # pozadie
        # tmave pozadie okolo dosky (poziadavka: cierna plocha okolo mriezky)
        p.fillRect(self.rect(), QColor(0, 0, 0))

        # vykresli bunky s premiami
        for r in range(15):
            for c in range(15):
                rect = QRectF(x0 + c * cell, y0 + r * cell, cell, cell)
                # premium farba
                premium = self.board.cells[r][c].premium
                color = QColor(240, 240, 240)
                if premium == Premium.DL:
                    color = QColor(153, 204, 255)
                elif premium == Premium.TL:
                    color = QColor(51, 153, 255)
                elif premium == Premium.DW:
                    color = QColor(255, 153, 204)
                elif premium == Premium.TW:
                    color = QColor(255, 102, 102)
                p.fillRect(rect, color)
                # mriezka
                p.setPen(QPen(QColor(200, 200, 200)))
                p.drawRect(rect)

        # hviezda v strede
        star_rect = QRectF(x0 + 7 * cell, y0 + 7 * cell, cell, cell)
        p.setPen(QPen(QColor(120, 120, 120)))
        font = QFont()
        font.setPointSizeF(cell * 0.4)
        p.setFont(font)
        p.drawText(star_rect, int(Qt.AlignmentFlag.AlignCenter), "★")

        # existujuce pismena
        for r in range(15):
            for c in range(15):
                ch = self.board.cells[r][c].letter
                if not ch:
                    continue
                rect = QRectF(x0 + c * cell, y0 + r * cell, cell, cell)
                # odlis blank
                if self.board.cells[r][c].is_blank:
                    p.fillRect(rect.adjusted(cell*0.1, cell*0.1, -cell*0.1, -cell*0.1), QColor(255, 255, 255))
                    p.setPen(QPen(QColor(160, 160, 160)))
                    p.drawEllipse(rect.center(), cell*0.06, cell*0.06)
                p.setPen(QPen(QColor(0, 0, 0)))
                f = QFont()
                f.setBold(True)
                f.setPointSizeF(cell * 0.45)
                p.setFont(f)
                p.drawText(rect, int(Qt.AlignmentFlag.AlignCenter), ch)

        # pending pismena (prekrytie, jemny tien)
        for pl in self._pending:
            r, c = pl.row, pl.col
            rect = QRectF(x0 + c * cell, y0 + r * cell, cell, cell)
            p.fillRect(rect.adjusted(cell*0.1, cell*0.1, -cell*0.1, -cell*0.1), QColor(255, 255, 224))
            p.setPen(QPen(QColor(0, 0, 0)))
            f = QFont()
            f.setBold(True)
            f.setPointSizeF(cell * 0.45)
            p.setFont(f)
            txt = pl.blank_as if (pl.letter == "?" and pl.blank_as) else pl.letter
            p.drawText(rect, int(Qt.AlignmentFlag.AlignCenter), txt)

        # zvyraznenie poslednych poloziek tahu (jemny halo/obrys)
        if self._last_move_cells:
            for (r, c) in self._last_move_cells:
                rect = QRectF(x0 + c * cell, y0 + r * cell, cell, cell)
                # jemny vonkajsi halo
                halo = QColor(255, 215, 0, 90)  # zlaty priesvitny
                p.fillRect(rect, halo)
                # obrys
                p.setPen(QPen(QColor(255, 180, 0, 180), max(1, int(cell * 0.06))))
                p.drawRect(rect.adjusted(cell*0.05, cell*0.05, -cell*0.05, -cell*0.05))

        # anim highlight
        if self._anim_cell is not None and self._anim_phase < 1.0:
            r, c = self._anim_cell
            rect = QRectF(x0 + c * cell, y0 + r * cell, cell, cell)
            alpha = int(150 * (1.0 - self._anim_phase))
            p.fillRect(rect, QColor(0, 200, 0, alpha))

    def set_tile_drop_handler(self, handler: Callable[[int, int, dict[str, Any]], bool]) -> None:
        self._drop_handler = handler

    def set_pending_drag_handler(self, handler: Callable[[dict[str, Any], Qt.DropAction], None]) -> None:
        self._pending_drag_handler = handler

    def dragEnterEvent(self, event):  # type: ignore[no-untyped-def]  # noqa: N802
        if self._accepts_mime(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):  # type: ignore[no-untyped-def]  # noqa: N802
        if self._accepts_mime(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):  # type: ignore[no-untyped-def]  # noqa: N802
        payload = self._decode_payload(event.mimeData())
        if payload is None or payload.get("origin") != "rack":
            event.ignore()
            return
        x0, y0, cell = self._grid_geometry()
        pos = event.position()
        x = pos.x()
        y = pos.y()
        if x < x0 or y < y0:
            event.ignore()
            return
        col = int((x - x0) // cell)
        row = int((y - y0) // cell)
        if not (0 <= row < 15 and 0 <= col < 15):
            event.ignore()
            return
        if self._drop_handler is None:
            event.ignore()
            return
        if self._drop_handler(row, col, payload):
            event.setDropAction(Qt.DropAction.MoveAction)
            event.accept()
            self.flash_cell(row, col)
        else:
            event.ignore()

    def mousePressEvent(self, ev: QMouseEvent) -> None:  # noqa: N802
        x0, y0, cell = self._grid_geometry()
        x = ev.position().x()
        y = ev.position().y()
        if x < x0 or y < y0:
            return
        col = int((x - x0) // cell)
        row = int((y - y0) // cell)
        if not (0 <= row < 15 and 0 <= col < 15):
            return
        if ev.button() == Qt.MouseButton.LeftButton:
            for placement in reversed(self._pending):
                if placement.row == row and placement.col == col:
                    self._drag_candidate = placement
                    self._drag_start_pos = ev.position().toPoint()
                    return
        self.cellClicked.emit(row, col)

    def mouseMoveEvent(self, ev: QMouseEvent) -> None:  # noqa: N802
        if (
            self._drag_candidate is not None
            and ev.buttons() & Qt.MouseButton.LeftButton
            and self._drag_start_pos is not None
            and (ev.position().toPoint() - self._drag_start_pos).manhattanLength() >= QApplication.startDragDistance()
        ):
            self._start_drag_from_board()
            return
        super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev: QMouseEvent) -> None:  # noqa: N802
        self._drag_candidate = None
        self._drag_start_pos = None
        super().mouseReleaseEvent(ev)

    def _start_drag_from_board(self) -> None:
        if self._drag_candidate is None:
            return
        payload = {
            "origin": "board",
            "row": self._drag_candidate.row,
            "col": self._drag_candidate.col,
            "letter": self._drag_candidate.letter,
            "blank_as": self._drag_candidate.blank_as,
        }
        mime = QMimeData()
        try:
            encoded = json.dumps(payload, ensure_ascii=True).encode("ascii")
        except Exception:
            self._drag_candidate = None
            self._drag_start_pos = None
            return
        mime.setData(TILE_MIME, encoded)
        drag = QDrag(self)
        drag.setMimeData(mime)
        size = QSize(44, 44)
        pixmap = QPixmap(size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setBrush(QColor(11, 61, 11))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(pixmap.rect(), 6, 6)
        painter.setPen(QColor(255, 255, 255))
        font = painter.font()
        font.setBold(True)
        font.setPointSize(24)
        painter.setFont(font)
        display_val = payload.get("blank_as") if payload.get("blank_as") and payload.get("letter") == "?" else payload.get("letter", "")
        display = "" if display_val is None else str(display_val)
        painter.drawText(pixmap.rect(), int(Qt.AlignmentFlag.AlignCenter), display)
        painter.end()
        drag.setPixmap(pixmap)
        drag.setHotSpot(pixmap.rect().center())
        result = drag.exec(Qt.DropAction.MoveAction)
        if self._pending_drag_handler is not None:
            self._pending_drag_handler(payload, result)
        self._drag_candidate = None
        self._drag_start_pos = None

    @staticmethod
    def _decode_payload(mime: QMimeData) -> Optional[dict[str, Any]]:
        if not mime.hasFormat(TILE_MIME):
            return None
        try:
            raw = mime.data(TILE_MIME)
            raw_bytes = cast(bytes, raw.data())
            text = raw_bytes.decode("ascii")
            data = json.loads(text)
        except Exception:
            return None
        if isinstance(data, dict):
            return cast(dict[str, Any], data)
        return None

    def _accepts_mime(self, mime: QMimeData) -> bool:
        payload = self._decode_payload(mime)
        return bool(payload and payload.get("origin") == "rack")


class RackListWidget(QListWidget):
    """List widget prispôsobený pre drag & drop kameňov."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.setDragEnabled(True)
        self.viewport().setAcceptDrops(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(False)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setDragDropMode(QListWidget.DragDropMode.DragOnly)

    def startDrag(self, supported_actions: Any) -> None:  # noqa: N802
        item = self.currentItem()
        if item is None:
            return
        payload = {
            "origin": "rack",
            "letter": item.text(),
            "rack_index": self.currentRow(),
        }
        mime = QMimeData()
        try:
            encoded = json.dumps(payload, ensure_ascii=True).encode("ascii")
        except Exception:
            return
        mime.setData(TILE_MIME, encoded)
        drag = QDrag(self)
        drag.setMimeData(mime)
        size = self.iconSize()
        if size.isEmpty():
            size = QSize(44, 44)
        pixmap = QPixmap(size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setBrush(QColor(11, 61, 11))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(pixmap.rect(), 6, 6)
        painter.setPen(QColor(255, 255, 255))
        font = painter.font()
        font.setBold(True)
        font.setPointSize(max(10, int(size.height() * 0.6)))
        painter.setFont(font)
        painter.drawText(pixmap.rect(), int(Qt.AlignmentFlag.AlignCenter), item.text())
        painter.end()
        drag.setPixmap(pixmap)
        drag.setHotSpot(pixmap.rect().center())
        drag.exec(Qt.DropAction.MoveAction)

    def dragEnterEvent(self, event):  # type: ignore[no-untyped-def]  # noqa: N802
        if self._accepts_payload(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):  # type: ignore[no-untyped-def]  # noqa: N802
        if self._accepts_payload(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):  # type: ignore[no-untyped-def]  # noqa: N802
        if self._accepts_payload(event.mimeData()):
            event.setDropAction(Qt.DropAction.MoveAction)
            event.accept()
        else:
            event.ignore()

    @staticmethod
    def _accepts_payload(mime: QMimeData) -> bool:
        if not mime.hasFormat(TILE_MIME):
            return False
        try:
            raw = mime.data(TILE_MIME)
            raw_bytes = cast(bytes, raw.data())
            text = raw_bytes.decode("ascii")
            data = json.loads(text)
        except Exception:
            return False
        if not isinstance(data, dict):
            return False
        return data.get("origin") == "board"



class RackView(QWidget):
    """Jednoduchy rack bez DnD - klik na pismenko a potom na dosku (MVP zatial bez prekliku)."""
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # nizsi pas racku; bude presne sirky na 7 pismen
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 6, 0, 0)
        h.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.list = RackListWidget()
        self.list.setViewMode(QListWidget.ViewMode.IconMode)
        self.list.setResizeMode(QListWidget.ResizeMode.Adjust)
        # nastavenie velkosti jednej dlazdice
        self._tile_px = 44
        self._spacing_px = 6
        self.list.setIconSize(QSize(self._tile_px, self._tile_px))
        self.list.setGridSize(QSize(self._tile_px, self._tile_px))
        self.list.setSpacing(self._spacing_px)
        self.list.setWrapping(False)
        self.list.setFlow(QListView.Flow.LeftToRight)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.setFixedHeight(self._tile_px)
        # tmavozelene pozadie racku
        self.list.setStyleSheet(
            "QListWidget{background-color:#0b3d0b;border:0;} "
            "QListWidget::item{color:white;}"
        )
        # pseudo-3D tieň
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(12)
        shadow.setOffset(0, 2)
        shadow.setColor(QColor(0, 0, 0, 80))
        self.list.setGraphicsEffect(shadow)
        h.addWidget(self.list)
        total_height = self._tile_px + h.contentsMargins().top() + h.contentsMargins().bottom()
        self.setFixedHeight(total_height)

    def set_letters(self, letters: list[str]) -> None:
        self.list.clear()
        for ch in letters:
            item = QListWidgetItem(ch)
            font = item.font()
            font.setPointSize(18)
            font.setBold(True)
            item.setFont(font)
            self.list.addItem(item)
        # sirka presne na 7 pismen (bez ohladu na obsah)
        width_px = 7 * self._tile_px + 6 * self._spacing_px
        self.list.setFixedWidth(width_px)

    def take_selected(self) -> Optional[str]:
        it = self.list.currentItem()
        if it is None:
            return None
        ch = it.text()
        row = self.list.row(it)
        self.list.takeItem(row)
        return ch


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("ScrabGPT")
        self.resize(1000, 800)

        # Modely
        self._set_variant(get_active_variant_slug())
        self.board = Board(PREMIUMS_PATH)
        self.bag = TileBag(variant=self.variant_definition)
        # na zaciatku prazdny rack; pismena sa zoberu po "Nová hra"
        self.human_rack: list[str] = []
        self.ai_rack: list[str] = []
        self.pending: list[Placement] = []
        self.human_score: int = 0
        self.ai_score: int = 0
        self.last_move_points: int = 0
        # uloz rozpis posledneho tahu a bingo flag pre UI
        self._last_move_breakdown: list[tuple[str, int, int, int, int]] = []  # (word, base, letter_bonus, word_mult, total)
        self._last_move_bingo: bool = False

        # Repro mód nastavenia (iba runtime)
        # Pozn.: Nastavuje sa v dialógu Nastavenia a používa pri "Nová hra".
        self.repro_mode: bool = False
        self.repro_seed: int = 0

        # OpenAI klient (lazy init po prvom pouziti ak treba)
        self.ai_client: Optional[OpenAIClient] = None

        # UI
        self.toolbar = QToolBar()
        self.addToolBar(self.toolbar)

        self.act_new = QAction("🆕 Nová hra", self)
        self.act_new.triggered.connect(self._on_new_or_surrender)
        self.toolbar.addAction(self.act_new)

        self.act_settings = QAction("⚙️ Nastavenia", self)
        self.act_settings.triggered.connect(self.open_settings)
        self.toolbar.addAction(self.act_settings)

        self.act_log = QAction("📜 Zobraziť log…", self)
        self.act_log.triggered.connect(self.show_log)
        self.toolbar.addAction(self.act_log)

        # Save/Load
        self.act_save = QAction("💾 Uložiť…", self)
        self.act_save.triggered.connect(self.save_game_dialog)
        self.toolbar.addAction(self.act_save)
        self.act_open = QAction("📂 Otvoriť…", self)
        self.act_open.triggered.connect(self.open_game_dialog)
        self.toolbar.addAction(self.act_open)

        central = QWidget()
        self.setCentralWidget(central)
        v = QVBoxLayout(central)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        self.split = QSplitter(Qt.Orientation.Horizontal)
        v.addWidget(self.split)

        self.board_view = BoardView(self.board)
        self.board_view.cellClicked.connect(self.on_board_clicked)
        self.board_view.set_tile_drop_handler(self._handle_tile_drop_from_rack)
        self.board_view.set_pending_drag_handler(self._handle_pending_drag_finished)
        self.split.addWidget(self.board_view)

        # Pravý panel skóre
        self.score_panel = QWidget()
        spv = QVBoxLayout(self.score_panel)
        self.lbl_scores = QLabel()
        self.lbl_scores.setStyleSheet(
            "QLabel{font-size:20px;font-weight:600;color:#f0f0f0;}"
        )
        shadow_scores = QGraphicsDropShadowEffect(self.score_panel)
        shadow_scores.setBlurRadius(12)
        shadow_scores.setOffset(0, 2)
        shadow_scores.setColor(QColor(0, 0, 0, 150))
        self.lbl_scores.setGraphicsEffect(shadow_scores)
        spv.addWidget(self.lbl_scores)
        self.lbl_last_breakdown = QLabel("")
        self.lbl_last_breakdown.setWordWrap(True)
        self.lbl_last_breakdown.setStyleSheet(
            "QLabel{font-size:17px;color:#fafafa;}"
        )
        shadow_last = QGraphicsDropShadowEffect(self.score_panel)
        shadow_last.setBlurRadius(10)
        shadow_last.setOffset(0, 2)
        shadow_last.setColor(QColor(0, 0, 0, 130))
        self.lbl_last_breakdown.setGraphicsEffect(shadow_last)
        spv.addWidget(self.lbl_last_breakdown)
        self.btn_reroll = QPushButton("Opakovať žreb")
        self.btn_reroll.clicked.connect(self._on_repeat_starter_draw)
        spv.addWidget(self.btn_reroll)
        self.btn_confirm = QPushButton("Potvrdiť ťah")
        self.btn_confirm.clicked.connect(self.confirm_move)
        spv.addWidget(self.btn_confirm)
        self.btn_exchange = QPushButton("Vymeniť")
        self.btn_exchange.clicked.connect(self.exchange_human)
        spv.addWidget(self.btn_exchange)
        self.btn_reroll.hide()
        spv.addStretch(1)
        self.split.addWidget(self.score_panel)
        self.split.setSizes([700, 300])
        self._stored_split_sizes: list[int] = self.split.sizes()
        self._game_ui_visible: bool = True

        # Spodný pás: rack + status
        self.rack = RackView()
        v.addWidget(self.rack)
        self.status = QStatusBar()
        self.setStatusBar(self.status)
        # start: prazdny status bar
        self.status.showMessage("")

        # zobrazi prazdny rack, kym sa nespusti nova hra
        self.rack.set_letters(self.human_rack)

        # status spinner pri čakaní (AI/rozhodca)
        self._spinner_timer = QTimer(self)
        self._spinner_timer.setInterval(300)
        self._spinner_timer.timeout.connect(self._on_spinner_tick)
        self._spinner_phase = 0
        self._spinner_stack: list[_SpinnerEntry] = []
        self._wait_cursor_depth = 0
        self._ai_thinking: bool = False
        # Guard pre otvárací ťah AI (zabraňuje dvojitému volaniu pri štarte)
        self._ai_opening_active: bool = False
        self._consecutive_passes: int = 0
        self._pass_streak: dict[StarterSide, int] = {"HUMAN": 0, "AI": 0}
        self._no_moves_possible: bool = False
        self._game_over: bool = False
        self._game_end_reason: GameEndReason | None = None
        # interny stav pre AI judge callbacky
        self._ai_judge_words_coords: list[tuple[str, list[tuple[int, int]]]] = []
        self._ai_ps2: list[Placement] = []
        # flag jednorazového retry pre AI návrh
        self._ai_retry_used: bool = False
        # pomocné uloženie hlavného slova a anchoru pre retry po judge
        self._ai_last_main_word: str = ""
        self._ai_last_anchor: str = ""
        self._pending_words_coords: list[tuple[str, list[tuple[int, int]]]] = []
        self._starter_side: StarterSide | None = None
        self._starter_decided: bool = False

        self._reset_to_idle_state()

    def _set_variant(self, slug: str) -> None:
        try:
            definition = load_variant(slug)
        except Exception as exc:  # noqa: BLE001
            log.warning("variant_load_failed slug=%s error=%s", slug, exc)
            definition = load_variant(get_active_variant_slug())
            slug = definition.slug
        self.variant_slug = slug
        self.variant_definition = definition
        self.variant_language = definition.language

    @staticmethod
    def _analyze_judge_response(resp: dict[str, object]) -> tuple[bool, list[dict[str, Any]]]:
        """Derive overall validity and normalized entry list from judge response."""
        entries: list[dict[str, Any]] = []
        for key in ("results", "words"):
            value = resp.get(key)
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        entries.append(item)
        if not entries:
            if isinstance(resp.get("word"), str):
                entries.append(
                    {
                        "word": resp.get("word"),
                        "valid": bool(resp.get("valid", False)),
                        "reason": resp.get("reason"),
                    }
                )
        all_valid_flag = resp.get("all_valid")
        computed = all(bool(entry.get("valid", False)) for entry in entries) if entries else None
        if all_valid_flag is not None:
            all_valid = bool(all_valid_flag) if computed is None else bool(all_valid_flag) and bool(computed)
        elif computed is not None:
            all_valid = bool(computed)
        else:
            all_valid = bool(resp.get("valid", False))
        return all_valid, entries

    def new_game(self) -> None:
        # Základný placeholder pre žreb štartéra (MVP skeleton)
        from ..core.tiles import TileBag
        self.board = Board(PREMIUMS_PATH)
        self.board_view.board = self.board
        self._set_game_ui_visible(True)
        # Repro: ak je zapnutý, inicializuj tašku s daným seedom, inak náhodne
        seed_to_use: int | None = self.repro_seed if self.repro_mode else None
        self.bag = TileBag(seed=seed_to_use, variant=self.variant_definition)
        self._consecutive_passes = 0
        self._pass_streak = {"HUMAN": 0, "AI": 0}
        self._no_moves_possible = False
        self._game_over = False
        self._game_end_reason = None
        # zaloguj spustenie hry s nastaveniami repro (presny format pre acceptance)
        try:
            log.info("game_start seed=%s repro=%s", str(self.repro_seed if self.repro_mode else "-") , "true" if self.repro_mode else "false")
        except Exception:
            pass
        # žreb štartéra
        a = self.bag.draw(1)[0]
        b = self.bag.draw(1)[0]
        self.bag.put_back([a, b])
        start_message, starter_side = self._evaluate_starting_draw(a, b)
        self.human_rack = self.bag.draw(7)
        self.ai_rack = self.bag.draw(7)
        self.rack.set_letters(self.human_rack)
        self.human_score = 0
        self.ai_score = 0
        self.last_move_points = 0
        self._last_move_breakdown = []
        self._last_move_bingo = False
        self.board_view.set_last_move_cells([])
        self._update_scores_label()
        self.act_new.setText("🏳️ Vzdať sa")
        self._apply_starting_draw_result(start_message, starter_side)

    def _evaluate_starting_draw(self, human_tile: str, ai_tile: str) -> tuple[str, StarterSide | None]:
        starter_label = "hráč"
        starter_side: StarterSide | None = "HUMAN"
        if human_tile == "?" and ai_tile != "?":
            starter_label = "hráč"
            starter_side = "HUMAN"
        elif ai_tile == "?" and human_tile != "?":
            starter_label = "AI"
            starter_side = "AI"
        elif human_tile == ai_tile:
            starter_label = "remíza — opakuj žreb"
            starter_side = None
        else:
            if human_tile < ai_tile:
                starter_label = "hráč"
                starter_side = "HUMAN"
            else:
                starter_label = "AI"
                starter_side = "AI"
        message = f"Hráč má {human_tile}, AI má {ai_tile} → začína {starter_label}."
        return message, starter_side

    def _apply_starting_draw_result(self, message: str, starter_side: StarterSide | None) -> None:
        self.status.showMessage(message)
        self._ai_opening_active = False
        if starter_side is None:
            self._starter_side = None
            self._starter_decided = False
            self._set_starter_controls(decided=False)
            self._disable_human_inputs()
            return
        self._starter_side = starter_side
        self._starter_decided = True
        self._set_starter_controls(decided=True)
        if starter_side == "HUMAN":
            self._enable_human_inputs()
        else:
            self._disable_human_inputs()
            self._maybe_trigger_ai_opening()

    def _handle_starting_draw(self) -> None:
        human_tile = self.bag.draw(1)[0]
        ai_tile = self.bag.draw(1)[0]
        self.bag.put_back([human_tile, ai_tile])
        message, starter_side = self._evaluate_starting_draw(human_tile, ai_tile)
        self._apply_starting_draw_result(message, starter_side)

    def _on_repeat_starter_draw(self) -> None:
        if self._starter_decided:
            return
        self._handle_starting_draw()

    def _set_starter_controls(self, *, decided: bool) -> None:
        self.btn_reroll.setVisible(not decided)
        self.btn_reroll.setEnabled(not decided)
        self.btn_confirm.setVisible(decided)
        self.btn_exchange.setVisible(decided)

    def _maybe_trigger_ai_opening(self) -> None:
        try:
            empty = is_board_empty(self.board)
            auto = should_auto_trigger_ai_opening("AI", empty)
        except Exception:
            empty = False
            auto = False
        if auto and not self._ai_thinking and not self._ai_opening_active:
            self._ai_opening_active = True
            try:
                log.info("ai_opening start board_empty=%s", "true" if empty else "false")
            except Exception:
                pass
            self._start_ai_turn()

    def surrender(self) -> None:
        # okamzity koniec so zapisom vitaza
        winner = "AI" if self.human_score < self.ai_score else "Hráč"
        QMessageBox.information(self, "Koniec", f"{winner} vyhráva (vzdané).")
        self._reset_to_idle_state()

    def _reset_to_idle_state(self) -> None:
        """Vráti aplikáciu do východzieho stavu pred spustením hry."""
        # zastav animácie/spinner a ukonči rozbehnuté vlákna
        self._clear_spinner_state()
        self._ai_thinking = False
        self._ai_opening_active = False
        self._starter_side = None
        self._starter_decided = False
        self._ai_judge_words_coords = []
        self._ai_ps2 = []
        self._ai_retry_used = False
        self._ai_last_main_word = ""
        self._ai_last_anchor = ""
        for attr in ("_judge_thread", "_ai_thread", "_ai_judge_thread"):
            thread = getattr(self, attr, None)
            if isinstance(thread, QThread):
                try:
                    thread.requestInterruption()
                except Exception:
                    pass
                thread.quit()
                thread.wait(500)
            setattr(self, attr, None)
        # reset modelov
        self.board = Board(PREMIUMS_PATH)
        self.board_view.board = self.board
        self.pending = []
        self.board_view.set_pending(self.pending)
        self.board_view.set_last_move_cells([])
        self.board_view.update()
        self.human_rack = []
        self.ai_rack = []
        self.bag = TileBag(variant=self.variant_definition)
        self.rack.set_letters(self.human_rack)
        self.human_score = 0
        self.ai_score = 0
        self.last_move_points = 0
        self._last_move_breakdown = []
        self._last_move_bingo = False
        self._pending_words_coords = []
        self._consecutive_passes = 0
        self._pass_streak = {"HUMAN": 0, "AI": 0}
        self._no_moves_possible = False
        self._game_over = False
        self._game_end_reason = None
        self.lbl_last_breakdown.setText("")
        self._update_scores_label()
        self.status.showMessage("")
        self.act_new.setText("🆕 Nová hra")
        self._set_game_ui_visible(False)
        self._disable_human_inputs()
        self._set_starter_controls(decided=True)

    def _update_scores_label(self) -> None:
        self.lbl_scores.setText(
            f"<div>Skóre — Hráč: <b>{self.human_score}</b> | AI: <b>{self.ai_score}</b></div>"
            f"<div>Taška: {self.bag.remaining()}</div>"
        )
        self._update_last_move_breakdown_ui()

    def _update_last_move_breakdown_ui(self) -> None:
        """Aktualizuje panel rozpisu 'Posledný ťah'."""
        if not self._last_move_breakdown and not self._last_move_bingo:
            self.lbl_last_breakdown.setText("<div style='margin-bottom:6px'>Posledný ťah: -</div>")
            return
        lines: list[str] = []
        for (w, base, lb, mult, total) in self._last_move_breakdown:
            line = (
                f"<span style='font-weight:bold'>{w}</span>: základ {base}, "
                f"písmená +{lb}, násobok ×{mult} → <span style='font-weight:bold'>{total}</span>"
            )
            lines.append(line)
        if self._last_move_bingo:
            lines.append("<span style='color:#9cff9c'>+50 bingo</span>")
        html = "<br/>".join(lines)
        prefix = f"Posledný ťah: +{self.last_move_points}" if self.last_move_points else "Posledný ťah:"
        self.lbl_last_breakdown.setText(f"<div style='margin-bottom:6px'>{prefix}</div>{html}")

    def _append_pending_tile(self, placement: Placement) -> None:
        """Pridá dočasne položené písmeno a refreshne UI."""
        self.pending.append(placement)
        self.board_view.set_pending(self.pending)
        self.board_view.flash_cell(placement.row, placement.col)
        self._update_ghost_score()

    def _handle_tile_drop_from_rack(self, row: int, col: int, payload: dict[str, Any]) -> bool:
        if self.board.cells[row][col].letter:
            self.status.showMessage("Pole je obsadené.", 2000)
            return False
        if any(p.row == row and p.col == col for p in self.pending):
            self.status.showMessage("Pole už obsahuje dočasné písmeno.", 2000)
            return False
        letter = str(payload.get("letter", ""))
        rack_index = int(payload.get("rack_index", -1))
        idx_to_use: Optional[int] = None
        if 0 <= rack_index < len(self.human_rack) and self.human_rack[rack_index] == letter:
            idx_to_use = rack_index
        else:
            for i, ch in enumerate(self.human_rack):
                if ch == letter:
                    idx_to_use = i
                    break
        if idx_to_use is None:
            return False
        blank_as: Optional[str] = None
        if letter == "?":
            blank_as = self._choose_blank_letter()
            if blank_as is None:
                return False
        placement = Placement(row=row, col=col, letter=letter, blank_as=blank_as)
        self._append_pending_tile(placement)
        self.human_rack.pop(idx_to_use)
        self.rack.set_letters(self.human_rack)
        return True

    def _handle_pending_drag_finished(self, payload: dict[str, Any], action: Qt.DropAction) -> None:
        del action  # action slúži len ako informatívny údaj, spracovanie je rovnaké
        row = int(payload.get("row", -1))
        col = int(payload.get("col", -1))
        removed: Optional[Placement] = None
        for idx, placement in enumerate(self.pending):
            if placement.row == row and placement.col == col:
                removed = self.pending.pop(idx)
                break
        if removed is None:
            return
        self.board_view.set_pending(self.pending)
        self.board_view.update()
        self.human_rack.append(removed.letter)
        self.rack.set_letters(self.human_rack)
        self._update_ghost_score()

    def on_board_clicked(self, row: int, col: int) -> None:
        """Klik na dosku: ak je vybrate pismeno v racku a bunka je prazdna, poloz ho."""
        # existujuca alebo pending obsadena bunka?
        if self.board.cells[row][col].letter:
            return
        if any(p.row == row and p.col == col for p in self.pending):
            return
        ch = self.rack.take_selected()
        if ch is None:
            self.status.showMessage("Vyber písmeno v racku…", 2000)
            return
        blank_as: Optional[str] = None
        if ch == "?":
            sel = self._choose_blank_letter()
            if sel is None:
                # vrat pismenko do racku ak zrusil
                self.human_rack.append("?")
                self.rack.set_letters(self.human_rack)
                return
            blank_as = sel
        placement = Placement(row=row, col=col, letter=ch, blank_as=blank_as)
        self._append_pending_tile(placement)
        try:
            self.human_rack.remove(ch)
        except ValueError:
            pass
        self.rack.set_letters(self.human_rack)

    def _choose_blank_letter(self) -> Optional[str]:
        """Zobrazi popup s volbou A–Z pre blank a vrati vybrane pismeno."""
        dlg = QDialog(self)
        dlg.setWindowTitle("Vyber písmeno pre blank")
        grid = QGridLayout(dlg)
        letters = [chr(ord('A') + i) for i in range(26)]
        selected: dict[str, str] = {}
        def on_click(ch: str) -> None:
            selected['v'] = ch
            dlg.accept()
        for i, ch in enumerate(letters):
            btn = QPushButton(ch)
            btn.clicked.connect(lambda _=False, c=ch: on_click(c))
            r = i // 8
            c = i % 8
            grid.addWidget(btn, r, c)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        btns.rejected.connect(dlg.reject)
        grid.addWidget(btns, 4, 0, 1, 8)
        ok = dlg.exec()
        if ok and 'v' in selected:
            return selected['v']
        return None

    def _update_ghost_score(self) -> None:
        """Spocita a zobrazi ghost skore pre docasne pismena (vratane krizov)."""
        if not self.pending:
            self.status.showMessage("Hrá hráč…")
            return
        # docasne poloz na dosku
        self.board.place_letters(self.pending)
        # ziskaj slova
        words_found = extract_all_words(self.board, self.pending)
        words_coords = [(wf.word, wf.letters) for wf in words_found]
        score, _ = score_words(self.board, self.pending, words_coords)
        # vycisti docasne
        self.board.clear_letters(self.pending)
        self.status.showMessage(f"Ghost skóre: {score}")

    def _set_wait_cursor_active(self, active: bool) -> None:
        if active:
            if self._wait_cursor_depth == 0:
                QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            self._wait_cursor_depth += 1
            return
        if self._wait_cursor_depth <= 0:
            self._wait_cursor_depth = 0
            return
        self._wait_cursor_depth -= 1
        if self._wait_cursor_depth == 0:
            try:
                QApplication.restoreOverrideCursor()
            except Exception:
                pass

    def _emit_spinner_message(self) -> None:
        if not self._spinner_stack:
            return
        entry = self._spinner_stack[-1]
        if not entry.base_text:
            return
        dots = "." * (1 + (self._spinner_phase % 3))
        self.status.showMessage(f"{entry.base_text}{dots}")

    def _start_status_spinner(self, owner: str, base_text: str, *, wait_cursor: bool) -> None:
        for idx, entry in enumerate(self._spinner_stack):
            if entry.owner == owner:
                removed = self._spinner_stack.pop(idx)
                if removed.wait_cursor:
                    self._set_wait_cursor_active(False)
                break
        new_entry = _SpinnerEntry(owner=owner, base_text=base_text, wait_cursor=wait_cursor)
        self._spinner_stack.append(new_entry)
        if wait_cursor:
            self._set_wait_cursor_active(True)
        self._spinner_phase = 0
        if not self._spinner_timer.isActive():
            self._spinner_timer.start()
        self._emit_spinner_message()
        self._spinner_phase += 1

    def _stop_status_spinner(self, owner: str) -> None:
        for idx, entry in enumerate(self._spinner_stack):
            if entry.owner != owner:
                continue
            removed = self._spinner_stack.pop(idx)
            if removed.wait_cursor:
                self._set_wait_cursor_active(False)
            if not self._spinner_stack:
                self._spinner_timer.stop()
                self._spinner_phase = 0
                return
            if idx == len(self._spinner_stack):
                self._spinner_phase = 0
                self._emit_spinner_message()
                self._spinner_phase += 1
            return

    def _clear_spinner_state(self) -> None:
        self._spinner_timer.stop()
        self._spinner_phase = 0
        self._spinner_stack.clear()
        while self._wait_cursor_depth > 0:
            self._set_wait_cursor_active(False)

    def _on_spinner_tick(self) -> None:
        if not self._spinner_stack:
            return
        self._emit_spinner_message()
        self._spinner_phase += 1

    def _has_any_letters(self) -> bool:
        for r in range(15):
            for c in range(15):
                if self.board.cells[r][c].letter:
                    return True
        return False

    def _register_scoreless_turn(self, side: StarterSide) -> None:
        self._pass_streak[side] = self._pass_streak.get(side, 0) + 1
        self._consecutive_passes += 1

    def _register_scoring_turn(self, side: StarterSide) -> None:
        self._pass_streak[side] = 0
        self._consecutive_passes = 0
        self._no_moves_possible = False

    def _validate_move(self) -> Optional[str]:
        """Overi pravidla tahu, vrati chybovu spravu alebo None ak je OK."""
        if not self.pending:
            return "Najprv polož aspoň jedno písmeno."
        dir_ = placements_in_line(self.pending)
        if dir_ is None:
            return "Písmená musia byť v jednej línii."
        if not no_gaps_in_line(self.board, self.pending, dir_):
            return "V hlavnej línii sú diery."
        if not self._has_any_letters():
            if not first_move_must_cover_center(self.pending):
                return "Prvý ťah musí prechádzať stredom (★)."
        else:
            if not connected_to_existing(self.board, self.pending):
                return "Ťah musí nadväzovať na existujúce písmená."
        return None

    def confirm_move(self) -> None:
        """Potvrdí ťah: validácia, rozhodca, aplikácia ťahu (alebo chybová hláška)."""
        # prirad trace_id pre tento ľudský ťah
        TRACE_ID_VAR.set(str(uuid.uuid4())[:8])
        log.info("[HUMAN] start turn")
        err = self._validate_move()
        if err is not None:
            QMessageBox.warning(self, "Pravidlá", err)
            return
        # docasne poloz, ziskaj slova a drz ich pre scoring
        self.board.place_letters(self.pending)
        words_found = extract_all_words(self.board, self.pending)
        words_coords = [(wf.word, wf.letters) for wf in words_found]
        words = [wf.word for wf in words_found]
        log.info("Rozhodca overuje slová: %s", words)
        # spusti spinner (online judge)
        self._start_status_spinner("judge", "Rozhoduje rozhodca", wait_cursor=True)

        # lazy init klienta
        if self.ai_client is None:
            self.ai_client = OpenAIClient()

        # worker v pozadi na rozhodcu
        class JudgeWorker(QObject):
            finished: Signal = Signal(dict)
            failed: Signal = Signal(Exception)
            def __init__(self, client: OpenAIClient, words: list[str], trace_id: str, language: str) -> None:
                super().__init__()
                self.client = client
                self.words = words
                self.trace_id = trace_id
                self.language = language
            def run(self) -> None:
                try:
                    TRACE_ID_VAR.set(self.trace_id)
                    resp = self.client.judge_words(self.words, language=self.language)
                    self.finished.emit(resp)
                except Exception as e:  # noqa: BLE001
                    self.failed.emit(e)

        self._judge_thread = QThread(self)
        self._judge_worker = JudgeWorker(self.ai_client, words, TRACE_ID_VAR.get(), self.variant_language)
        self._judge_worker.moveToThread(self._judge_thread)
        self._judge_thread.started.connect(self._judge_worker.run)
        self._judge_worker.finished.connect(self._on_judge_ok)
        self._judge_worker.failed.connect(self._on_judge_fail)
        # uklon thread po dokonceni
        self._judge_worker.finished.connect(self._judge_thread.quit)
        self._judge_worker.failed.connect(self._judge_thread.quit)
        # uchovaj pre neskor pouzitie pri skore
        self._pending_words_coords = words_coords
        self._judge_thread.start()

    def _on_judge_ok(self, resp: dict[str, object]) -> None:
        self._stop_status_spinner("judge")
        log.info("Rozhodca výsledok: %s", resp)
        all_valid, entries = self._analyze_judge_response(resp)
        if not all_valid:
            bad = ""
            bad_reason = ""
            for it in entries:
                if not bool(it.get("valid", False)):
                    bad = str(it.get("word", ""))
                    bad_reason = str(it.get("reason", ""))
                    break
            # zmaz docasne (rack ostáva nezmenený)
            self.board.clear_letters(self.pending)
            self.pending = []
            self.rack.set_letters(self.human_rack)
            self.board_view.set_pending(self.pending)
            self.status.showMessage("Hrá hráč…")
            msg = f"Neplatné slovo: {bad}" if bad else "Neplatný ťah"
            if bad_reason:
                msg = f"{msg}\nDôvod: {bad_reason}"
            QMessageBox.information(self, "Neplatný ťah", msg)
            return

        # validne: spocitaj skore + bingo, aplikuj prémie a dopln rack
        words_coords = getattr(self, "_pending_words_coords")
        total, _bd = score_words(self.board, self.pending, words_coords)
        # uloz rozpis pre UI
        self._last_move_breakdown = [(bd.word, bd.base_points, bd.letter_bonus_points, bd.word_multiplier, bd.total) for bd in _bd]
        self._last_move_bingo = (len(self.pending) == 7)
        # zvyrazni posledne polozene bunky
        self.board_view.set_last_move_cells([(p.row, p.col) for p in self.pending])
        if len(self.pending) == 7:
            total += 50
        apply_premium_consumption(self.board, self.pending)
        self.last_move_points = total
        self.human_score += total
        # spotrebuj rack presne o pouzite pismena a dopln z tasky
        before = "".join(self.human_rack)
        used = ",".join(p.letter for p in self.pending)
        new_rack = consume_rack(self.human_rack, self.pending)
        draw_cnt = max(0, 7 - len(new_rack))
        drawn = self.bag.draw(draw_cnt) if draw_cnt > 0 else []
        new_rack.extend(drawn)
        self.human_rack = new_rack
        try:
            log.info(
                'rack_update side=human used="%s" before="%s" after="%s" drawn=%s bag_remaining=%s',
                used,
                before,
                "".join(self.human_rack),
                len(drawn),
                self.bag.remaining(),
            )
        except Exception:
            pass
        # vycisti pending a UI
        self.pending = []
        self.board_view.set_pending(self.pending)
        self.rack.set_letters(self.human_rack)
        self._update_scores_label()
        self._register_scoring_turn("HUMAN")
        self._check_endgame()
        if self._game_over:
            return
        # spusti AI tah
        self._start_ai_turn()

    def _on_judge_fail(self, e: Exception) -> None:
        self._stop_status_spinner("judge")
        log.exception("Rozhodca zlyhal: %s", e)
        # vrat dosku do stavu pred potvrdenim (rack ostáva nezmenený)
        self.board.clear_letters(self.pending)
        self.pending = []
        self.rack.set_letters(self.human_rack)
        self.board_view.set_pending(self.pending)
        self.status.showMessage("Hrá hráč…")
        QMessageBox.critical(self, "Chyba rozhodcu", str(e))

    # ---------- AI tah ----------
    def _disable_human_inputs(self) -> None:
        self.btn_confirm.setEnabled(False)
        self.board_view.setEnabled(False)
        self.rack.setEnabled(False)
        self.btn_exchange.setEnabled(False)

    def _enable_human_inputs(self) -> None:
        self.btn_confirm.setEnabled(True)
        self.board_view.setEnabled(True)
        self.rack.setEnabled(True)
        self.btn_exchange.setEnabled(True)

    def exchange_human(self) -> None:
        """Vymena vybranych kamienkov v racku (ak taska ma >=7)."""
        if self._ai_thinking:
            return
        # ťah hráča (výmena) – vlastné trace_id
        TRACE_ID_VAR.set(str(uuid.uuid4())[:8])
        log.info("[HUMAN] start exchange")
        if self.bag.remaining() < 7:
            QMessageBox.information(self, "Vymeniť", "Taška má menej ako 7 kameňov – výmena nie je povolená.")
            return
        # pozbieraj vybrane polozky
        selected: list[str] = [it.text() for it in self.rack.list.selectedItems()]
        if not selected:
            QMessageBox.information(self, "Vymeniť", "Vyber aspoň jeden kameň na výmenu.")
            return
        # Odober z racku presne tieto znaky (podla poradia selectu) a vymen
        tmp_rack = self.human_rack.copy()
        for ch in selected:
            if ch in tmp_rack:
                tmp_rack.remove(ch)
            else:
                QMessageBox.warning(self, "Vymeniť", "Vybraný kameň sa nenašiel v racku.")
                return
        self.status.showMessage("Hráč vymieňa…")
        new_tiles = self.bag.exchange(selected)
        self.human_rack = tmp_rack + new_tiles
        self.rack.set_letters(self.human_rack)
        self._update_scores_label()
        # vymena konci kolo ako pass
        self._register_scoreless_turn("HUMAN")
        self._check_endgame()
        if self._game_over:
            self._disable_human_inputs()
            return
        # spusti AI tah
        self._start_ai_turn()

    def _start_ai_turn(self) -> None:
        self._ai_thinking = True
        self._disable_human_inputs()
        self._start_status_spinner("ai", "Hrá AI", wait_cursor=True)
        # reset flagu pre nový ťah
        self._ai_retry_used = False
        # priraď trace_id pre AI ťah
        TRACE_ID_VAR.set(str(uuid.uuid4())[:8])
        log.info("[AI] start turn")
        if self.ai_client is None:
            self.ai_client = OpenAIClient()
        # priprav stav
        st = build_ai_state_dict(
            self.board, self.ai_rack, self.human_score, self.ai_score, turn="AI"
        )
        compact = (
            "grid:\n" + "\n".join(st["grid"]) +
            f"\nblanks:{st['blanks']}\n"
            f"ai_rack:{st['ai_rack']}\n"
            f"scores: H={st['human_score']} AI={st['ai_score']}\nturn:{st['turn']}\n"
        )

        class ProposeWorker(QObject):
            finished: Signal = Signal(dict)
            failed: Signal = Signal(Exception)
            def __init__(self, client: OpenAIClient, state_str: str, trace_id: str, variant: VariantDefinition) -> None:
                super().__init__()
                self.client = client
                self.state_str = state_str
                self.trace_id = trace_id
                self.variant = variant
            def run(self) -> None:
                try:
                    TRACE_ID_VAR.set(self.trace_id)
                    # Použi vylepšený prompt z ai.player
                    resp = ai_propose_move(
                        client=self.client,
                        compact_state=self.state_str,
                        variant=self.variant,
                    )
                    self.finished.emit(resp)
                except Exception as e:  # noqa: BLE001
                    self.failed.emit(e)

        self._ai_thread = QThread(self)
        self._ai_worker = ProposeWorker(self.ai_client, compact, TRACE_ID_VAR.get(), self.variant_definition)
        self._ai_worker.moveToThread(self._ai_thread)
        self._ai_thread.started.connect(self._ai_worker.run)
        self._ai_worker.finished.connect(self._on_ai_proposal)
        self._ai_worker.failed.connect(self._on_ai_fail)
        self._ai_worker.finished.connect(self._ai_thread.quit)
        self._ai_worker.failed.connect(self._ai_thread.quit)
        self._ai_thread.start()

    def _validate_ai_move(self, proposal: dict[str, object]) -> Optional[str]:
        # zakladna validacia schema a rack
        if bool(proposal.get("exchange")):
            return "AI navrhla exchange — odmietame v tomto slici."
        if bool(proposal.get("pass", False)):
            return None  # pass povoleny
        placements_obj = proposal.get("placements", [])
        if not isinstance(placements_obj, list) or not placements_obj:
            return "Žiadne placements v návrhu."
        # validacia rozsahu a linie
        try:
            placements_list: list[dict[str, Any]] = cast(list[dict[str, Any]], placements_obj)
            ps: list[Placement] = [
                Placement(int(p["row"]), int(p["col"]), str(p["letter"]))
                for p in placements_list
            ]
        except Exception:
            return "Placements nemajú správny tvar."
        # nesmie prepisovať existujúce písmená
        for p in ps:
            if self.board.cells[p.row][p.col].letter:
                return "AI sa pokúsila položiť na obsadené pole."
        dir_ = placements_in_line(ps)
        if dir_ is None:
            return "AI ťah nie je v jednej línii."
        # dopln blank_as z response ak je
        blanks = proposal.get("blanks", [])
        blank_map: dict[tuple[int,int], str] = {}
        if isinstance(blanks, list):
            for b in blanks:
                if not ("row" in b and "col" in b and "as" in b):
                    return "Blanks položky majú zlý formát."
                rr = int(b["row"])
                cc = int(b["col"])
                ch = str(b["as"])
                blank_map[(rr, cc)] = ch
        # skontroluj diery s ohladom na existujuce pismena
        if not no_gaps_in_line(self.board, ps, dir_):
            return "AI ťah má diery."
        # po prvom tahu over spojitost
        if not self._has_any_letters():
            if not first_move_must_cover_center(ps):
                return "AI prvý ťah nejde cez stred."
        else:
            if not connected_to_existing(self.board, ps):
                return "AI ťah nenadväzuje."
        # skontroluj rack AI (pocet a pouzitie blankov)
        # Pozn.: AI moze poslat v placements realne pismeno (napr. 'E')
        # a zaroven v `blanks` uviesť, ze na daných súradniciach ide o blank
        # mapovaný na 'E'. V takom prípade musíme spotrebovať '?' z racku,
        # nie písmeno 'E'.
        rack_copy = self.ai_rack.copy()
        for p in ps:
            consume_as_blank = (p.row, p.col) in blank_map
            if p.letter == "?" or consume_as_blank:
                if "?" in rack_copy:
                    rack_copy.remove("?")
                else:
                    return "AI použila viac blankov než má."
            else:
                if p.letter in rack_copy:
                    rack_copy.remove(p.letter)
                else:
                    return "AI použila písmeno, ktoré nemá."
        # ak blanky, musia mat mapovanie
        for p in ps:
            if p.letter == "?" and (p.row, p.col) not in blank_map:
                return "AI použila blank bez 'blanks' mapovania."
        return None

    def _on_ai_proposal(self, proposal: dict[str, object]) -> None:
        log.info("AI navrhla: %s", proposal)
        # validacia / retry / pass
        err = self._validate_ai_move(proposal)
        if err is not None and not bool(proposal.get("pass", False)):
            # jeden retry s hintom
            self.status.showMessage("AI návrh neplatný, skúša znova…")
            self._spinner_phase = 0
            self._spinner_timer.start()
            if self.ai_client is None:
                self.ai_client = OpenAIClient()
            # Špecifický hint pre porušenie center-star pravidla pri prvom ťahu
            if (not self._has_any_letters()) and ("stred" in err or "center" in err or err.startswith("AI prvý ťah")):
                hint = "Opening rule: your first move must cross the center star at H8. Propose a different move."
            else:
                hint = f"Previous error: {err}. Ensure single line, no gaps, valid rack."
            st = build_ai_state_dict(self.board, self.ai_rack, self.human_score, self.ai_score, turn="AI")
            compact = (
                "grid:\n" + "\n".join(st["grid"]) +
                f"\nblanks:{st['blanks']}\n"
                f"ai_rack:{st['ai_rack']}\n"
                f"scores: H={st['human_score']} AI={st['ai_score']}\nturn:{st['turn']}\n"
            )
            try:
                # označ, že prebehol retry (pre logovanie výsledku otvorenia)
                self._ai_retry_used = True
                proposal = ai_propose_move(
                    self.ai_client,
                    compact_state=compact,
                    variant=self.variant_definition,
                    retry_hint=hint,
                )
            except TokenBudgetExceededError:
                # špeciálna hláška, ale AI iba pasuje, aby sa hra nezasekla
                self._stop_status_spinner("ai")
                self._ai_thinking = False
                self._enable_human_inputs()
                self._register_scoreless_turn("AI")
                self.status.showMessage("AI minula tokeny — pasuje")
                if self._ai_opening_active:
                    try:
                        log.info("ai_opening done result=%s", "invalid_retry_pass" if self._ai_retry_used else "pass")
                    except Exception:
                        pass
                    self._ai_opening_active = False
                self._check_endgame()
                return
            except Exception as e:  # noqa: BLE001
                self._on_ai_fail(e)
                return
            err = self._validate_ai_move(proposal)
            if err is not None and not bool(proposal.get("pass", False)):
                proposal = {"pass": True}

        if bool(proposal.get("pass", False)):
            self._stop_status_spinner("ai")
            self._ai_thinking = False
            self._enable_human_inputs()
            self._register_scoreless_turn("AI")
            self.status.showMessage("AI pasuje")
            if self._ai_opening_active:
                try:
                    log.info("ai_opening done result=%s", "invalid_retry_pass" if self._ai_retry_used else "pass")
                except Exception:
                    pass
                self._ai_opening_active = False
            self._check_endgame()
            return

        # aplikuj navrhnute placements (len docasne) a ziskaj slova
        board_was_empty = not self._has_any_letters()
        placements_obj = proposal.get("placements", [])
        placements_list: list[dict[str, Any]] = cast(list[dict[str, Any]], placements_obj) if isinstance(placements_obj, list) else []
        ps: list[Placement] = [
            Placement(int(p["row"]), int(p["col"]), str(p["letter"]))
            for p in placements_list
        ]
        blanks = proposal.get("blanks", [])
        blank_map: dict[tuple[int, int], str] = {}
        if isinstance(blanks, list):
            for b in cast(list[dict[str, Any]], blanks):
                rr = int(b["row"])
                cc = int(b["col"])
                ch = str(b["as"])
                blank_map[(rr, cc)] = ch
        # nastav blank_as; ak AI oznacila v `blanks`, prekonvertuj na '?'
        ps2: list[Placement] = []
        for p in ps:
            if (p.row, p.col) in blank_map:
                ps2.append(Placement(p.row, p.col, "?", blank_as=blank_map[(p.row,p.col)]))
            else:
                ps2.append(p)
        self.board.place_letters(ps2)
        words_found = extract_all_words(self.board, ps2)
        words_coords = [(wf.word, wf.letters) for wf in words_found]
        words = [wf.word for wf in words_found]
        log.info("AI slová na overenie: %s", words)

        # --- Kontrola zlepeného hlavného slova vs. deklarované 'word' ---
        def _infer_main_and_anchor() -> tuple[str, str]:
            """Zistí hlavné slovo a anchor (existujúci prefix/sufix).

            Komentár (SK): Vyberieme to slovo z `words_found`, ktoré obsahuje
            všetky nové súradnice v jednej osi. Anchor určíme ako existujúcu
            časť na začiatku alebo konci (písmená mimo `ps2`).
            """
            placements_set = {(p.row, p.col) for p in ps2}
            # hľadaj slovo, ktoré pokrýva všetky nové pozície
            main_word = ""
            main_coords: list[tuple[int, int]] = []
            for wf in words_found:
                coords = [(r, c) for (r, c) in wf.letters]
                if all((r, c) in coords for (r, c) in placements_set):
                    main_word = wf.word
                    main_coords = coords
                    break
            if not main_word and words_found:
                # fallback: vyber najdlhšie slovo
                wf = max(words_found, key=lambda x: len(x.word))
                main_word = wf.word
                main_coords = [(r, c) for (r, c) in wf.letters]
            # anchor = existujúce písmená na krajoch
            prefix = []
            suffix = []
            for _idx, (r, c) in enumerate(main_coords):
                if (r, c) not in placements_set:
                    prefix.append((r, c))
                else:
                    break
            for idx in range(len(main_coords) - 1, -1, -1):
                rc = main_coords[idx]
                if rc not in placements_set:
                    suffix.append(rc)
                else:
                    break
            # premen na texty
            def letter_at(rc: tuple[int, int]) -> str:
                return self.board.cells[rc[0]][rc[1]].letter or ""
            anchor_text = ""
            if prefix:
                anchor_text = "".join(letter_at(rc) for rc in prefix)
            if suffix:
                suf_txt = "".join(letter_at(rc) for rc in reversed(suffix))
                anchor_text = anchor_text + ("+" if anchor_text and suf_txt else "") + suf_txt
            return main_word, anchor_text

        main_word, anchor = _infer_main_and_anchor()
        self._ai_last_main_word = main_word
        self._ai_last_anchor = anchor

        declared = str(proposal.get("word", "")).strip()
        if (
            declared
            and main_word
            and declared.upper() != main_word.upper()
            and not board_was_empty
            and not self._ai_retry_used
            and not bool(proposal.get("pass", False))
        ):
            # Mismatch = pravdepodobné lepenie na existujúci reťazec
            self.board.clear_letters(ps2)
            self._spinner_phase = 0
            self._spinner_timer.start()
            self._ai_retry_used = True
            try:
                log.info("ai_retry reason=invalid_glued_word main=%s anchor=%s", main_word, anchor)
            except Exception:
                pass
            st = build_ai_state_dict(self.board, self.ai_rack, self.human_score, self.ai_score, turn="AI")
            compact = (
                "grid:\n" + "\n".join(st["grid"]) +
                f"\nblanks:{st['blanks']}\n"
                f"ai_rack:{st['ai_rack']}\n"
                f"scores: H={st['human_score']} AI={st['ai_score']}\nturn:{st['turn']}\n"
            )
            hint = (
                f"Your previous move created an invalid glued word '{main_word}' by attaching to existing '{anchor}'. "
                f"Propose a different move that forms a single valid {self.variant_language} word; prefer proper hooks or overlaps. Return JSON only."
            )
            try:
                new_prop = ai_propose_move(
                    self.ai_client if self.ai_client else OpenAIClient(),
                    compact_state=compact,
                    variant=self.variant_definition,
                    retry_hint=hint,
                )
            except Exception as e:  # noqa: BLE001
                self._on_ai_fail(e)
                return
            # Re-validate and continue with new proposal
            self._on_ai_proposal(new_prop)
            return

        # Rozhodovanie (online)
        class JudgeWorker(QObject):
            finished: Signal = Signal(dict)
            failed: Signal = Signal(Exception)
            def __init__(self, client: OpenAIClient, words: list[str], trace_id: str, language: str) -> None:
                super().__init__()
                self.client = client
                self.words = words
                self.trace_id = trace_id
                self.language = language
            def run(self) -> None:
                try:
                    TRACE_ID_VAR.set(self.trace_id)
                    resp = self.client.judge_words(self.words, language=self.language)
                    self.finished.emit(resp)
                except Exception as e:  # noqa: BLE001
                    self.failed.emit(e)

        self._ai_judge_words_coords = words_coords
        self._ai_ps2 = ps2
        # spusti spinner pre online rozhodovanie AI
        self._start_status_spinner("judge", "Rozhoduje rozhodca", wait_cursor=True)
        self._ai_judge_thread = QThread(self)
        self._ai_judge_worker = JudgeWorker(
            self.ai_client if self.ai_client else OpenAIClient(),
            words,
            TRACE_ID_VAR.get(),
            self.variant_language,
        )
        self._ai_judge_worker.moveToThread(self._ai_judge_thread)
        self._ai_judge_thread.started.connect(self._ai_judge_worker.run)
        self._ai_judge_worker.finished.connect(self._on_ai_judge_ok)
        self._ai_judge_worker.failed.connect(self._on_ai_judge_fail)
        self._ai_judge_worker.finished.connect(self._ai_judge_thread.quit)
        self._ai_judge_worker.failed.connect(self._ai_judge_thread.quit)
        self._ai_judge_thread.start()

    def _on_ai_fail(self, e: Exception) -> None:
        self._stop_status_spinner("ai")
        self._ai_thinking = False
        self._enable_human_inputs()
        log.exception("AI navrh zlyhal: %s", e)
        self.status.showMessage("AI pasuje (chyba)")
        self._register_scoreless_turn("AI")
        if self._ai_opening_active:
            try:
                log.info("ai_opening done result=%s", "invalid_retry_pass" if self._ai_retry_used else "pass")
            except Exception:
                pass
            self._ai_opening_active = False
        self._check_endgame()

    def _on_ai_judge_ok(self, resp: dict[str, object]) -> None:
        self._stop_status_spinner("judge")
        self._stop_status_spinner("ai")
        all_valid, entries = self._analyze_judge_response(resp)
        if not all_valid:
            # guided retry ak ešte neprebehol
            if not self._ai_retry_used:
                ps2 = getattr(self, "_ai_ps2")
                self.board.clear_letters(ps2)
                self._ai_retry_used = True
                invalid_word = ""
                invalid_reason = ""
                for it in entries:
                    if not bool(it.get("valid", False)):
                        invalid_word = str(it.get("word", ""))
                        invalid_reason = str(it.get("reason", ""))
                        break
                try:
                    log.info(
                        "ai_retry reason=judge_invalid word=%s reason=%s",
                        invalid_word or self._ai_last_main_word,
                        invalid_reason,
                    )
                except Exception:
                    pass
                st = build_ai_state_dict(self.board, self.ai_rack, self.human_score, self.ai_score, turn="AI")
                compact = (
                    "grid:\n" + "\n".join(st["grid"]) +
                    f"\nblanks:{st['blanks']}\n"
                    f"ai_rack:{st['ai_rack']}\n"
                    f"scores: H={st['human_score']} AI={st['ai_score']}\nturn:{st['turn']}\n"
                )
                summary_word = invalid_word or self._ai_last_main_word or ""
                summary_reason = invalid_reason or self._ai_last_anchor or ""
                if summary_reason:
                    hint_reason = f" (reason: {summary_reason})"
                else:
                    hint_reason = ""
                hint = (
                    f"Judge rejected your previous move '{summary_word}'.{hint_reason} "
                    f"Propose a different move that forms a single valid {self.variant_language} word; prefer proper hooks or overlaps. Return JSON only."
                )
                try:
                    new_prop = ai_propose_move(
                        self.ai_client if self.ai_client else OpenAIClient(),
                        compact_state=compact,
                        variant=self.variant_definition,
                        retry_hint=hint,
                    )
                except Exception as e:  # noqa: BLE001
                    self._on_ai_fail(e)
                    return
                self._on_ai_proposal(new_prop)
                return
            # inak: pass
            self.board.clear_letters(getattr(self, "_ai_ps2"))
            self._ai_thinking = False
            self._enable_human_inputs()
            self.status.showMessage("AI navrhla neplatné slovo — pass")
            self._register_scoreless_turn("AI")
            self._check_endgame()
            return
        # validne: spocitaj, aplikuj prémie, refill
        words_coords = self._ai_judge_words_coords
        ps2 = self._ai_ps2
        total, _bd = score_words(self.board, ps2, words_coords)
        # rozpis pre UI (posledny tah = AI tah)
        self._last_move_breakdown = [(bd.word, bd.base_points, bd.letter_bonus_points, bd.word_multiplier, bd.total) for bd in _bd]
        self._last_move_bingo = (len(ps2) == 7)
        self.board_view.set_last_move_cells([(p.row, p.col) for p in ps2])
        if len(ps2) == 7:
            total += 50
        apply_premium_consumption(self.board, ps2)
        self.ai_score += total
        # spotrebuj rack AI a doplň z tašky
        before = "".join(self.ai_rack)
        used = ",".join(p.letter for p in ps2)
        new_rack = consume_rack(self.ai_rack, ps2)
        draw_cnt = max(0, 7 - len(new_rack))
        drawn = self.bag.draw(draw_cnt) if draw_cnt > 0 else []
        new_rack.extend(drawn)
        self.ai_rack = new_rack
        try:
            log.info(
                'rack_update side=ai used="%s" before="%s" after="%s" drawn=%s bag_remaining=%s',
                used,
                before,
                "".join(self.ai_rack),
                len(drawn),
                self.bag.remaining(),
            )
        except Exception:
            pass
        self._update_scores_label()
        self._ai_thinking = False
        self._enable_human_inputs()
        self.status.showMessage("Hrá hráč…")
        self._register_scoring_turn("AI")
        if self._ai_opening_active:
            try:
                log.info("ai_opening done result=%s", "applied")
            except Exception:
                pass
            self._ai_opening_active = False
        self._check_endgame()

    def _on_ai_judge_fail(self, e: Exception) -> None:
        self._stop_status_spinner("judge")
        self._stop_status_spinner("ai")
        log.exception("AI judge zlyhal: %s", e)
        self.board.clear_letters(getattr(self, "_ai_ps2", []))
        self._ai_thinking = False
        self._enable_human_inputs()
        self.status.showMessage("AI pasuje (chyba rozhodcu)")
        self._register_scoreless_turn("AI")
        if self._ai_opening_active:
            try:
                log.info("ai_opening done result=%s", "invalid_retry_pass" if self._ai_retry_used else "pass")
            except Exception:
                pass
            self._ai_opening_active = False
        self._check_endgame()

    def _check_endgame(self) -> None:
        if self._game_over:
            return
        reason = determine_end_reason(
            bag_remaining=self.bag.remaining(),
            racks={"HUMAN": self.human_rack, "AI": self.ai_rack},
            pass_streaks=self._pass_streak,
            no_moves_available=self._no_moves_possible,
        )
        if reason is None:
            return

        players = [
            PlayerState("HUMAN", self.human_rack.copy(), self.human_score),
            PlayerState("AI", self.ai_rack.copy(), self.ai_score),
        ]
        leftover = apply_final_scoring(players)
        human_state = next(p for p in players if p.name == "HUMAN")
        ai_state = next(p for p in players if p.name == "AI")
        self.human_score = human_state.score
        self.ai_score = ai_state.score
        self._update_scores_label()
        self._game_over = True
        self._game_end_reason = reason
        self._disable_human_inputs()
        self._ai_thinking = False

        if reason == GameEndReason.BAG_EMPTY_AND_PLAYER_OUT:
            if not self.human_rack and self.ai_rack:
                winner = "Hráč"
            elif not self.ai_rack and self.human_rack:
                winner = "AI"
            else:
                winner = None
            if winner is not None:
                msg = f"Koniec hry. Víťaz: {winner}."
            else:
                msg = "Koniec hry."
        elif reason == GameEndReason.NO_MOVES_AVAILABLE:
            msg = "Koniec hry. Ďalší ťah nie je možný."
        else:
            msg = "Koniec hry. Obaja hráči dvakrát po sebe pasovali."

        def _format_leftover() -> str:
            parts = []
            human_left = leftover.get("HUMAN", 0)
            ai_left = leftover.get("AI", 0)
            if human_left:
                parts.append(f"Hráč -{human_left}")
            if ai_left:
                parts.append(f"AI -{ai_left}")
            return " " + " | ".join(parts) if parts else ""

        QMessageBox.information(self, "Koniec", msg + _format_leftover())

    def open_settings(self) -> None:
        dlg = SettingsDialog(self, repro_mode=self.repro_mode, repro_seed=self.repro_seed)
        ok = dlg.exec()
        if ok:
            try:
                if self.ai_client is not None:
                    self.ai_client.ai_move_max_output_tokens = int(os.getenv("AI_MOVE_MAX_OUTPUT_TOKENS", "3600"))
                    self.ai_client.judge_max_output_tokens = int(os.getenv("JUDGE_MAX_OUTPUT_TOKENS", "800"))
            except Exception:
                pass

            self.repro_mode = bool(dlg.repro_check.isChecked())
            try:
                self.repro_seed = int(dlg.seed_edit.text().strip() or "0")
            except ValueError:
                self.repro_seed = 0

            new_variant_slug = getattr(dlg, "selected_variant_slug", self.variant_slug)
            if isinstance(new_variant_slug, str) and new_variant_slug and new_variant_slug != self.variant_slug:
                self._set_variant(new_variant_slug)
                self.status.showMessage(
                    f"Variant nastavený na {self.variant_language}. Spusti novú hru, aby sa zmena prejavila.",
                    5000,
                )
            else:
                self.status.showMessage("Nastavenia uložené.", 2000)

    def _set_game_ui_visible(self, visible: bool) -> None:
        """Prepína panel so skóre a rackom podľa toho, či je aktívna hra."""
        if visible == self._game_ui_visible:
            return
        if visible:
            self.score_panel.show()
            self.rack.show()
            if self._stored_split_sizes:
                self.split.setSizes(self._stored_split_sizes)
            self._game_ui_visible = True
        else:
            self._stored_split_sizes = self.split.sizes()
            self.score_panel.hide()
            self.rack.hide()
            self.split.setSizes([1, 0])
            self._game_ui_visible = False

    def _on_new_or_surrender(self) -> None:
        if self.act_new.text().startswith("🏳️"):
            self.surrender()
        else:
            self.new_game()

    def show_log(self) -> None:
        dlg = LogViewerDialog(self, max_lines=500)
        dlg.exec()

    # ---------- Save/Load ----------
    def save_game_dialog(self) -> None:
        from PySide6.QtWidgets import QFileDialog
        # zruš pending placements (neukladáme dočasné zmeny)
        if self.pending:
            self.board.clear_letters(self.pending)
            self.pending = []
            self.board_view.set_pending(self.pending)
            self.rack.set_letters(self.human_rack)
        from pathlib import Path
        path, _ = QFileDialog.getSaveFileName(self, "Uložiť hru", str(Path.home()), "JSON (*.json)")
        if not path:
            return
        try:
            st = build_save_state_dict(
                board=self.board,
                human_rack=self.human_rack,
                ai_rack=self.ai_rack,
                bag=self.bag,
                human_score=self.human_score,
                ai_score=self.ai_score,
                turn=("AI" if self._ai_thinking else "HUMAN"),
                last_move_cells=getattr(self.board_view, "_last_move_cells", []),
                last_move_points=self.last_move_points,
                consecutive_passes=self._consecutive_passes,
                human_pass_streak=self._pass_streak.get("HUMAN", 0),
                ai_pass_streak=self._pass_streak.get("AI", 0),
                game_over=self._game_over,
                game_end_reason=(self._game_end_reason.name if self._game_end_reason else ""),
                repro=self.repro_mode,
                seed=self.repro_seed,
            )
            import json
            from pathlib import Path
            with Path(path).open("w", encoding="utf-8") as f:
                json.dump(st, f, ensure_ascii=False, indent=2)
            log.info("game_save path=%s schema=1", path)
            self.status.showMessage("Hra uložená.", 2000)
        except Exception as e:  # noqa: BLE001
            log.exception("Save failed: %s", e)
            QMessageBox.critical(self, "Uložiť", f"Chyba ukladania: {e}")

    def open_game_dialog(self) -> None:
        from PySide6.QtWidgets import QFileDialog
        from pathlib import Path
        path, _ = QFileDialog.getOpenFileName(self, "Otvoriť hru", str(Path.home()), "JSON (*.json)")
        if not path:
            return
        import json
        from pathlib import Path
        try:
            with Path(path).open(encoding="utf-8") as f:
                data = json.load(f)
            st = parse_save_state_dict(data)
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "Otvoriť", f"Neplatný súbor: {e}")
            return
        try:
            # obnov board, bag a hodnoty
            saved_variant = st.get("variant")
            if isinstance(saved_variant, str):
                self._set_variant(saved_variant)
            self.board = restore_board_from_save(st, PREMIUMS_PATH)
            self.board_view.board = self.board
            self.human_rack = list(st.get("human_rack", ""))
            self.ai_rack = list(st.get("ai_rack", ""))
            self.bag = restore_bag_from_save(st)
            self.human_score = int(st.get("human_score", 0))
            self.ai_score = int(st.get("ai_score", 0))
            self.last_move_points = int(st.get("last_move_points", 0))
            # last move highlight
            lm = [(pos["row"], pos["col"]) for pos in st.get("last_move_cells", [])]
            self.board_view.set_last_move_cells(lm)
            self._consecutive_passes = int(st.get("consecutive_passes", 0))
            self._pass_streak = {
                "HUMAN": int(st.get("human_pass_streak", 0)),
                "AI": int(st.get("ai_pass_streak", 0)),
            }
            self._game_over = bool(st.get("game_over", False))
            self._no_moves_possible = False
            reason_name = st.get("game_end_reason", "")
            try:
                self._game_end_reason = GameEndReason[reason_name] if reason_name else None
            except KeyError:
                self._game_end_reason = None
            # zruš pending
            self.pending = []
            self.board_view.set_pending(self.pending)
            # repro info
            self.repro_mode = bool(st.get("repro", False))
            self.repro_seed = int(st.get("seed", 0))
            # UI refresh
            self.rack.set_letters(self.human_rack)
            self._set_game_ui_visible(True)
            self._update_scores_label()
            self.status.showMessage("Hra načítaná.", 2000)
            if self._game_over:
                self._disable_human_inputs()
            log.info("game_load path=%s schema=1", path)
        except Exception as e:  # noqa: BLE001
            log.exception("Load failed: %s", e)
            QMessageBox.critical(self, "Otvoriť", f"Zlyhalo načítanie: {e}")

def main() -> None:
    app = QApplication(sys.argv)

    # Globálny excepthook: log + toast
    def _excepthook(exc_type, exc, tb):  # type: ignore[no-untyped-def]
        from contextlib import suppress
        with suppress(Exception):
            logging.getLogger("scrabgpt").exception("Unhandled exception", exc_info=(exc_type, exc, tb))
        # jednoduchý toast
        with suppress(Exception):
            QMessageBox.critical(None, "Neošetrená výnimka", str(exc))
    sys.excepthook = _excepthook

    w = MainWindow()
    w.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
