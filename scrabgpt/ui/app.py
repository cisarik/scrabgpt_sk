from __future__ import annotations
import os
import sys
import uuid
import json
import logging
import html
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal, Optional, Sequence, cast
from pathlib import Path
from PySide6.QtCore import (
    Qt,
    QSize,
    QRect,
    QRectF,
    QTimer,
    Signal,
    QObject,
    QThread,
    QPoint,
    QPointF,
    QEasingCurve,
    QVariantAnimation,
    QMimeData,
    QModelIndex,
)
from PySide6.QtGui import (
    QAction,
    QPainter,
    QColor,
    QPen,
    QFont,
    QMouseEvent,
    QPaintEvent,
    QIntValidator,
    QTextCursor,
    QPixmap,
    QDrag,
    QLinearGradient,
    QPainterPath,
    QBrush,
)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QToolBar, QLabel, QSplitter, QStatusBar, QMessageBox, QPushButton,
    QDialog, QFormLayout, QLineEdit, QDialogButtonBox, QListWidget, QListWidgetItem,
    QGridLayout, QGraphicsDropShadowEffect, QListView, QPlainTextEdit, QCheckBox,
    QComboBox, QSizePolicy, QStyleOptionViewItem, QStyledItemDelegate, QStyle, QButtonGroup,
    QFrame,
    QAbstractButton,
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
from ..core.rules import placements_in_line
from ..core.rules import first_move_must_cover_center, connected_to_existing, no_gaps_in_line, extract_all_words
from ..core.scoring import score_words, apply_premium_consumption
from ..core.types import Placement, Premium
from ..ai.client import OpenAIClient
from ..ai.player import propose_move as ai_propose_move
from ..ai.player import should_auto_trigger_ai_opening, is_board_empty
from ..ai.openrouter import OpenRouterClient
from ..ai.multi_model import propose_move_multi_model
from .prompt_editor import PromptEditorDialog
from .agents_dialog import AgentsDialog
from .agent_status_widget import AgentStatusWidget
from ..core.state import build_ai_state_dict
from ..core.rack import consume_rack, restore_rack
from ..core.state import build_save_state_dict, parse_save_state_dict, restore_board_from_save, restore_bag_from_save
from ..core.variant_store import (
    VariantDefinition,
    get_active_variant_slug,
    list_installed_variants,
    load_variant,
    set_active_variant_slug,
)
from ..core.opponent_mode import OpponentMode
from ..ai.variants import (
    LanguageInfo,
    download_and_store_variant,
    fetch_supported_languages,
    get_languages_for_ui,
    match_language,
)
from ..ai.agent_config import discover_agents, get_default_agents_dir, get_agent_by_name
from ..ai.internet_tools import register_internet_tools
from .model_results import AIModelResultsTable

ASSETS = str(Path(__file__).parent / ".." / "assets")
PREMIUMS_PATH = get_premiums_path()
ROOT_DIR = Path(__file__).resolve().parents[2]
ENV_PATH = str(ROOT_DIR / ".env")
LOG_PATH = default_log_path()
EUR_PER_TOKEN = 0.00000186  # 1 token ≈ 0.00000186 EUR (zadané majiteľom)

DEFAULT_OPENROUTER_TIMEOUT = 120
OPENROUTER_TIMEOUT_CHOICES: list[tuple[int, str]] = [
    (30, "30 sekúnd"),
    (60, "1 minúta"),
    (120, "2 minúty"),
    (180, "3 minúty"),
    (300, "5 minút"),
]

TILE_MIME = "application/x-scrabgpt-tile"

# Typ alias pre strany pri určovaní štartéra
StarterSide = Literal["HUMAN", "AI"]

@dataclass(frozen=True)
class _SpinnerEntry:
    owner: str
    base_text: str
    wait_cursor: bool


@dataclass(frozen=True)
class _WordScoreDetail:
    word: str
    base_points: int
    letter_bonus_points: int
    word_multiplier: int
    total: int
    reason: str
    lexicons: tuple[str, ...] = field(default_factory=tuple)
    definitions: tuple[str, ...] = field(default_factory=tuple)
    examples: tuple[str, ...] = field(default_factory=tuple)
    notes: str = ""

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

    def _draw_letter_tile(
        self,
        painter: QPainter,
        cell_rect: QRectF,
        cell_size: float,
        *,
        glyph: str,
        is_blank: bool,
        pending: bool,
    ) -> None:
        """Renderuje stvorec kameňa so zaoblenými rohmi priamo na doske."""
        painter.save()
        margin = cell_size * 0.12
        tile_rect = cell_rect.adjusted(margin, margin, -margin, -margin)
        corner = cell_size * 0.20
        shadow_offset = cell_size * 0.05

        shadow_path = QPainterPath()
        shadow_path.addRoundedRect(
            tile_rect.translated(0, shadow_offset),
            corner,
            corner,
        )
        shadow_alpha = 60 if pending else 80
        painter.fillPath(shadow_path, QColor(0, 0, 0, shadow_alpha))

        tile_path = QPainterPath()
        tile_path.addRoundedRect(tile_rect, corner, corner)
        gradient = QLinearGradient(tile_rect.topLeft(), tile_rect.bottomLeft())
        if pending:
            gradient.setColorAt(0.0, QColor(252, 252, 232))
            gradient.setColorAt(1.0, QColor(232, 232, 204))
        elif is_blank:
            gradient.setColorAt(0.0, QColor(250, 250, 250))
            gradient.setColorAt(1.0, QColor(230, 230, 230))
        else:
            gradient.setColorAt(0.0, QColor(248, 248, 248))
            gradient.setColorAt(1.0, QColor(226, 226, 226))
        painter.fillPath(tile_path, QBrush(gradient))

        border_pen = QPen(QColor(150, 150, 150))
        border_pen.setWidthF(max(1.0, cell_size * 0.03))
        painter.setPen(border_pen)
        painter.drawPath(tile_path)

        text_pen = QPen(QColor(30, 30, 30))
        painter.setPen(text_pen)
        font = QFont()
        font.setBold(True)
        font.setPointSizeF(cell_size * 0.45)
        painter.setFont(font)
        painter.drawText(tile_rect, int(Qt.AlignmentFlag.AlignCenter), glyph)

        if is_blank:
            indicator_radius = cell_size * 0.045
            indicator_color = QColor(100, 100, 100, 150)
            painter.setBrush(indicator_color)
            painter.setPen(Qt.PenStyle.NoPen)
            center = tile_rect.center()
            painter.drawEllipse(center, indicator_radius, indicator_radius)

        painter.restore()

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
        center_has_letter = bool(self.board.cells[7][7].letter)
        if not center_has_letter:
            for pl in self._pending:
                if pl.row == 7 and pl.col == 7:
                    center_has_letter = True
                    break
        if not center_has_letter:
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
                self._draw_letter_tile(
                    p,
                    rect,
                    cell,
                    glyph=ch,
                    is_blank=self.board.cells[r][c].is_blank,
                    pending=False,
                )

        # pending pismena (prekrytie, jemny tien)
        for pl in self._pending:
            r, c = pl.row, pl.col
            rect = QRectF(x0 + c * cell, y0 + r * cell, cell, cell)
            glyph = pl.blank_as if (pl.letter == "?" and pl.blank_as) else pl.letter
            self._draw_letter_tile(
                p,
                rect,
                cell,
                glyph=glyph or "",
                is_blank=(pl.letter == "?"),
                pending=True,
            )

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
        if payload is None or payload.get("origin") not in {"rack", "board"}:
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
        return bool(payload and payload.get("origin") in {"rack", "board"})


class RackTileDelegate(QStyledItemDelegate):
    """Renderuje kamene v racku s jemným 3D efektom a podporou animácií."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._corner_radius = 7.0
        self._rack = cast("RackListWidget | None", parent)

    def paint(  # type: ignore[override]
        self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex
    ) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        if self._rack is not None:
            offset = self._rack.animation_offset_for_index(index)
            if offset is not None:
                painter.translate(offset)
            highlight_strength = self._rack.highlight_strength_for_index(index)
        else:
            highlight_strength = 0.0

        rect_attr = getattr(option, "rect", None)
        if not isinstance(rect_attr, QRect):
            painter.restore()
            return
        state_attr = getattr(option, "state", 0)
        if isinstance(state_attr, QStyle.StateFlag):
            state_flags = state_attr
        elif isinstance(state_attr, int):
            try:
                state_flags = QStyle.StateFlag(state_attr)
            except Exception:
                state_flags = QStyle.StateFlag(0)
        else:
            state_flags = QStyle.StateFlag(0)
        available = rect_attr.adjusted(3, 3, -3, -3)
        side = min(available.width(), available.height() - 2)
        cx = available.center().x()
        cy = available.center().y() - 1.0
        base_rect = QRectF(cx - side / 2.0, cy - side / 2.0, side, side)
        shadow_rect = base_rect.translated(0, 2)
        shadow_path = QPainterPath()
        shadow_path.addRoundedRect(shadow_rect, self._corner_radius, self._corner_radius)
        painter.fillPath(shadow_path, QColor(0, 0, 0, 70))

        tile_path = QPainterPath()
        tile_path.addRoundedRect(base_rect, self._corner_radius, self._corner_radius)
        gradient = QLinearGradient(base_rect.topLeft(), base_rect.bottomLeft())
        gradient.setColorAt(0.0, QColor(248, 248, 248))
        gradient.setColorAt(1.0, QColor(225, 225, 225))
        painter.fillPath(tile_path, QBrush(gradient))

        if bool(state_flags & QStyle.StateFlag.State_MouseOver):
            painter.fillPath(tile_path, QColor(140, 195, 140, 60))

        border_color = QColor(160, 160, 160)
        if bool(state_flags & QStyle.StateFlag.State_Selected):
            painter.fillPath(tile_path, QColor(80, 145, 100, 70))
            border_color = QColor(70, 125, 90)

        if highlight_strength > 0.0:
            glow_alpha = int(110 * min(1.0, highlight_strength))
            painter.fillPath(tile_path, QColor(255, 255, 210, glow_alpha))

        pen = QPen(border_color)
        pen.setWidthF(1.2)
        painter.setPen(pen)
        painter.drawPath(tile_path)

        display = index.data(Qt.ItemDataRole.DisplayRole)
        if isinstance(display, str) and display:
            text_pen = QPen(QColor(28, 60, 28))
            painter.setPen(text_pen)
            font = painter.font()
            font.setBold(True)
            font.setPointSizeF(max(12.0, base_rect.height() * 0.46))
            painter.setFont(font)
            painter.drawText(base_rect, int(Qt.AlignmentFlag.AlignCenter), display)

        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:  # type: ignore[override]
        del option, index
        return QSize(44, 44)


class RackListWidget(QListWidget):
    """List widget prispôsobený pre drag & drop kameňov s animovaným radením."""

    letters_reordered = Signal(list)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.setDragEnabled(True)
        self.viewport().setAcceptDrops(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(False)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setDragDropMode(QListWidget.DragDropMode.DragDrop)
        self._tile_delegate = RackTileDelegate(self)
        self.setItemDelegate(self._tile_delegate)
        self._reorder_animation: QVariantAnimation | None = None
        self._animation_deltas: dict[int, QPointF] = {}
        self._animation_offsets: dict[int, QPointF] = {}
        self._highlight_item_key: int | None = None
        self._highlight_strength: dict[int, float] = {}
        self._drop_gap_index: int | None = None

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
        drag_size = QSize(size.width() + 12, size.height() + 14)
        pixmap = QPixmap(drag_size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        outer = pixmap.rect().adjusted(5, 5, -5, -5)
        side = min(outer.width(), outer.height() - 2)
        center = outer.center()
        tile_rect = QRectF(
            center.x() - side / 2.0,
            center.y() - side / 2.0 - 1.0,
            side,
            side,
        )
        shadow_rect = tile_rect.translated(0, 2)
        shadow_path = QPainterPath()
        shadow_path.addRoundedRect(shadow_rect, 7, 7)
        painter.fillPath(shadow_path, QColor(0, 0, 0, 80))

        tile_path = QPainterPath()
        tile_path.addRoundedRect(tile_rect, 7, 7)
        gradient = QLinearGradient(tile_rect.topLeft(), tile_rect.bottomLeft())
        gradient.setColorAt(0.0, QColor(248, 248, 248))
        gradient.setColorAt(1.0, QColor(225, 225, 225))
        painter.fillPath(tile_path, QBrush(gradient))

        pen = QPen(QColor(150, 150, 150))
        pen.setWidthF(1.2)
        painter.setPen(pen)
        painter.drawPath(tile_path)

        painter.setPen(QColor(28, 60, 28))
        font = painter.font()
        font.setBold(True)
        font.setPointSize(max(12, int(tile_rect.height() * 0.46)))
        painter.setFont(font)
        painter.drawText(tile_rect, int(Qt.AlignmentFlag.AlignCenter), item.text())
        painter.end()
        drag.setPixmap(pixmap)
        drag.setHotSpot(pixmap.rect().center())
        drag.exec(Qt.DropAction.MoveAction)

    def dragEnterEvent(self, event):  # type: ignore[no-untyped-def]  # noqa: N802
        if self._decode_payload(event.mimeData()) is not None:
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):  # type: ignore[no-untyped-def]  # noqa: N802
        payload = self._decode_payload(event.mimeData())
        if payload is None:
            event.ignore()
            return
        origin = payload.get("origin")
        if origin == "rack":
            gap_index = self._insertion_index_from_pos(event.position())
            if gap_index != self._drop_gap_index:
                self._drop_gap_index = gap_index
                self.viewport().update()
        else:
            if self._drop_gap_index is not None:
                self._drop_gap_index = None
                self.viewport().update()
        event.acceptProposedAction()

    def dragLeaveEvent(self, event):  # type: ignore[no-untyped-def]  # noqa: N802
        del event
        if self._drop_gap_index is not None:
            self._drop_gap_index = None
            self.viewport().update()

    def dropEvent(self, event):  # type: ignore[no-untyped-def]  # noqa: N802
        payload = self._decode_payload(event.mimeData())
        if payload is None:
            event.ignore()
            return
        origin = payload.get("origin")
        handled = False
        if origin == "board":
            handled = True
        elif origin == "rack":
            handled = self._handle_internal_drop(payload, event.position())
        if handled:
            event.setDropAction(Qt.DropAction.MoveAction)
            event.accept()
        else:
            event.ignore()
        if self._drop_gap_index is not None:
            self._drop_gap_index = None
            self.viewport().update()

    def paintEvent(self, event: QPaintEvent) -> None:
        super().paintEvent(event)
        if self._drop_gap_index is None:
            return
        painter = QPainter(self.viewport())
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        gap_rect = self._indicator_rect(self._drop_gap_index)
        gradient = QLinearGradient(gap_rect.topLeft(), gap_rect.bottomLeft())
        gradient.setColorAt(0.0, QColor(255, 255, 255, 160))
        gradient.setColorAt(1.0, QColor(180, 220, 180, 60))
        painter.fillRect(gap_rect, gradient)

    def animation_offset_for_index(self, index: QModelIndex) -> QPointF | None:
        if not index.isValid():
            return None
        item = self.item(index.row())
        if item is None:
            return None
        return self._animation_offsets.get(id(item))

    def highlight_strength_for_index(self, index: QModelIndex) -> float:
        if not index.isValid():
            return 0.0
        item = self.item(index.row())
        if item is None:
            return 0.0
        return self._highlight_strength.get(id(item), 0.0)

    def reset_visual_state(self) -> None:
        if self._reorder_animation is not None:
            self._reorder_animation.stop()
            self._reorder_animation = None
        self._animation_deltas.clear()
        self._animation_offsets.clear()
        self._highlight_strength.clear()
        self._highlight_item_key = None
        self._drop_gap_index = None

    def _handle_internal_drop(self, payload: dict[str, Any], pos: QPointF) -> bool:
        origin_index = int(payload.get("rack_index", -1))
        if not (0 <= origin_index < self.count()):
            return False
        gap_index = self._insertion_index_from_pos(pos)
        if gap_index == -1:
            gap_index = self.count()
        target_index = gap_index
        if target_index > origin_index:
            target_index -= 1
        target_index = max(0, min(target_index, self.count() - 1))
        if target_index == origin_index:
            self._start_reorder_animation(self._capture_item_geometry(), self._capture_item_geometry(), self.item(origin_index))
            self.letters_reordered.emit(self._collect_letters())
            return True

        old_rects = self._capture_item_geometry()
        item = self.takeItem(origin_index)
        if item is None:
            return False
        self.insertItem(target_index, item)
        self.setCurrentItem(item)
        new_rects = self._capture_item_geometry()
        self._start_reorder_animation(old_rects, new_rects, item)
        self.letters_reordered.emit(self._collect_letters())
        return True

    def _capture_item_geometry(self) -> dict[int, QRectF]:
        geometries: dict[int, QRectF] = {}
        for row in range(self.count()):
            item = self.item(row)
            if item is None:
                continue
            index = self.indexFromItem(item)
            rect = QRectF(self.visualRect(index))
            geometries[id(item)] = rect
        return geometries

    def _start_reorder_animation(
        self,
        old_rects: dict[int, QRectF],
        new_rects: dict[int, QRectF],
        moved_item: QListWidgetItem | None,
    ) -> None:
        if self._reorder_animation is not None:
            self._reorder_animation.stop()
        deltas: dict[int, QPointF] = {}
        for key, old_rect in old_rects.items():
            new_rect = new_rects.get(key)
            if new_rect is None:
                continue
            delta = QPointF(
                old_rect.topLeft().x() - new_rect.topLeft().x(),
                old_rect.topLeft().y() - new_rect.topLeft().y(),
            )
            if abs(delta.x()) < 0.1 and abs(delta.y()) < 0.1:
                continue
            deltas[key] = delta
        self._animation_deltas = deltas
        self._highlight_item_key = id(moved_item) if moved_item is not None else None
        self._reorder_animation = QVariantAnimation(self)
        self._reorder_animation.setDuration(260)
        self._reorder_animation.setEasingCurve(QEasingCurve.Type.OutBack)
        self._reorder_animation.setStartValue(0.0)
        self._reorder_animation.setEndValue(1.0)
        self._reorder_animation.valueChanged.connect(self._apply_animation_frame)
        self._reorder_animation.finished.connect(self._finish_animation)
        self._apply_animation_frame(0.0)
        self._reorder_animation.start()

    def _apply_animation_frame(self, value: Any) -> None:
        try:
            progress = float(value)
        except (TypeError, ValueError):
            progress = 0.0
        remaining = max(0.0, 1.0 - progress)
        offsets: dict[int, QPointF] = {}
        for key, delta in self._animation_deltas.items():
            offset = QPointF(delta.x() * remaining, delta.y() * remaining)
            if abs(offset.x()) < 0.1 and abs(offset.y()) < 0.1:
                continue
            offsets[key] = offset
        self._animation_offsets = offsets
        if self._highlight_item_key is not None:
            strength = min(1.0, remaining)
            self._highlight_strength = {self._highlight_item_key: strength}
        else:
            self._highlight_strength = {}
        self.viewport().update()

    def _finish_animation(self) -> None:
        self._animation_offsets.clear()
        self._animation_deltas.clear()
        self._highlight_strength.clear()
        self._highlight_item_key = None
        if self._reorder_animation is not None:
            self._reorder_animation.deleteLater()
        self._reorder_animation = None
        self.viewport().update()

    def _insertion_index_from_pos(self, pos: QPointF) -> int:
        if self.count() == 0:
            return 0
        x = pos.x()
        best_index = self.count()
        for row in range(self.count()):
            item = self.item(row)
            if item is None:
                continue
            rect = self.visualRect(self.indexFromItem(item))
            center_x = rect.center().x()
            if x < center_x:
                best_index = row
                break
        return best_index

    def _indicator_rect(self, gap_index: int) -> QRectF:
        viewport_rect = QRectF(self.viewport().rect())
        height = viewport_rect.height() * 0.72
        top = viewport_rect.center().y() - height / 2.0
        if self.count() == 0:
            x = viewport_rect.center().x()
        elif gap_index <= 0:
            first_rect = QRectF(self.visualRect(self.indexFromItem(self.item(0))))
            x = first_rect.left()
        elif gap_index >= self.count():
            last_rect = QRectF(self.visualRect(self.indexFromItem(self.item(self.count() - 1))))
            x = last_rect.right()
        else:
            left_rect = QRectF(self.visualRect(self.indexFromItem(self.item(gap_index - 1))))
            right_rect = QRectF(self.visualRect(self.indexFromItem(self.item(gap_index))))
            x = (left_rect.right() + right_rect.left()) / 2.0
        indicator_width = 8.0
        return QRectF(x - indicator_width / 2.0, top, indicator_width, height)

    def _collect_letters(self) -> list[str]:
        letters: list[str] = []
        for i in range(self.count()):
            item = self.item(i)
            if item is None:
                continue
            letters.append(item.text())
        return letters

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
        if not isinstance(data, dict):
            return None
        return cast(dict[str, Any], data)




class RackView(QWidget):
    """Jednoduchy rack bez DnD - klik na pismenko a potom na dosku (MVP zatial bez prekliku)."""
    letters_reordered = Signal(list)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # nizsi pas racku; bude presne sirky na 7 pismen
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 6, 0, 0)
        h.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.list = RackListWidget()
        self.list.letters_reordered.connect(self.letters_reordered.emit)
        self.list.setViewMode(QListWidget.ViewMode.IconMode)
        self.list.setResizeMode(QListWidget.ResizeMode.Adjust)
        # nastavenie velkosti jednej dlazdice
        self._tile_px = 44
        self._spacing_px = 6
        self._rack_padding_px = 6
        self.list.setIconSize(QSize(self._tile_px, self._tile_px))
        self.list.setGridSize(QSize(self._tile_px + self._spacing_px, self._tile_px + self._spacing_px))
        self.list.setSpacing(0)
        self.list.setWrapping(False)
        self.list.setFlow(QListView.Flow.LeftToRight)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.setFixedHeight(self._tile_px + self._rack_padding_px * 2)
        # tmavozelene pozadie racku so slabým 3D gradientom
        self.list.setStyleSheet(
            "QListWidget{"
            "background:qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            "stop:0 #1a8c1a, stop:0.6 #147414, stop:1 #0b3d0b);"
            "border:1px solid #083508;"
            "border-radius:14px;"
            f"padding:{self._rack_padding_px}px;"
            "}"
        )
        # pseudo-3D tieň
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(12)
        shadow.setOffset(0, 2)
        shadow.setColor(QColor(20, 60, 20, 110))
        self.list.setGraphicsEffect(shadow)
        h.addWidget(self.list)
        total_height = (
            self._tile_px
            + self._rack_padding_px * 2
            + h.contentsMargins().top()
            + h.contentsMargins().bottom()
        )
        self.setFixedHeight(total_height)

    def set_letters(self, letters: list[str]) -> None:
        self.list.reset_visual_state()
        self.list.clear()
        for ch in letters:
            item = QListWidgetItem(ch)
            font = item.font()
            font.setPointSize(18)
            font.setBold(True)
            item.setFont(font)
            self.list.addItem(item)
        # sirka presne na 7 pismen (bez ohladu na obsah)
        width_px = (
            7 * self._tile_px
            + (7 - 1) * self._spacing_px
            + self._rack_padding_px * 2
        )
        self.list.setFixedWidth(width_px)

    def take_selected(self) -> Optional[str]:
        it = self.list.currentItem()
        if it is None:
            return None
        ch = it.text()
        row = self.list.row(it)
        self.list.takeItem(row)
        return ch

    def set_multi_selection_enabled(self, enabled: bool) -> None:
        """Toggle multi-selection mode together with drag behaviour."""
        mode = (
            QListWidget.SelectionMode.MultiSelection
            if enabled
            else QListWidget.SelectionMode.SingleSelection
        )
        self.list.setSelectionMode(mode)
        # Disable dragging while multi-selecting to avoid accidental DnD.
        self.list.setDragEnabled(not enabled)
        self.list.clearSelection()


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("ScrabGPT")
        self.resize(1000, 800)

        # Register internet tools
        register_internet_tools()
        
        # Opponent mode configuration
        self.opponent_mode = OpponentMode.BEST_MODEL
        self.selected_agent_name: Optional[str] = None
        self.available_agents = discover_agents(get_default_agents_dir())
        self.game_in_progress = False
        
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
        self._last_move_reason: str = ""
        self._last_move_reason_is_html: bool = False
        self._last_move_word_details: list[_WordScoreDetail] = []
        self._active_word_index: int | None = None

        # Repro mód nastavenia (iba runtime)
        # Pozn.: Nastavuje sa v dialógu Nastavenia a používa pri "Nová hra".
        self.repro_mode: bool = False
        self.repro_seed: int = 0
        
        # Agents dialog (non-modal, can stay open)
        self.agents_dialog: AgentsDialog | None = None
        
        # Agent workers (run in background even when dialog closed)
        self.agent_workers: dict[str, Any] = {}

        # OpenAI klient (lazy init po prvom pouziti ak treba)
        self.ai_client: Optional[OpenAIClient] = None
        
        # OpenRouter multi-model configuration
        self.use_multi_model: bool = False
        self.selected_ai_models: list[dict[str, Any]] = []
        self.openrouter_timeout_seconds: int = self._load_openrouter_timeout()
        self.ai_move_max_tokens, self._ai_tokens_from_env = self._load_ai_move_max_tokens()
        self._user_defined_ai_tokens: bool = False

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

        self.act_create_iq_test = QAction("🧠 Uložiť ako test", self)
        self.act_create_iq_test.triggered.connect(self.create_iq_test)
        self.toolbar.addAction(self.act_create_iq_test)
        
        # Add spacer to push following items to the right
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.toolbar.addWidget(spacer)
        
        # Create animated agent status widget
        self.agent_status_widget = AgentStatusWidget(self)
        self.toolbar.addWidget(self.agent_status_widget)
        
        self.act_agents = QAction("⚙️ Agenti", self)
        self.act_agents.triggered.connect(self.open_agents_dialog)
        self.toolbar.addAction(self.act_agents)

        central = QWidget()
        self.setCentralWidget(central)
        v = QVBoxLayout(central)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        self.split = QSplitter(Qt.Orientation.Horizontal)
        v.addWidget(self.split)

        self.board_view = BoardView(self.board)
        self.board_view.cellClicked.connect(self.on_board_clicked)
        self.board_view.set_tile_drop_handler(self._handle_tile_drop)
        self.board_view.set_pending_drag_handler(self._handle_pending_drag_finished)
        self.split.addWidget(self.board_view)

        # Pravý panel skóre
        self.score_panel = QWidget()
        spv = QVBoxLayout(self.score_panel)
        self.lbl_scores = QLabel()
        self.lbl_scores.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_scores.setStyleSheet(
            "QLabel {"
            "background-color: #4caf50;"
            "color: #0b1c00;"
            "font-size: 18px;"
            "font-weight: 600;"
            "padding: 10px 18px;"
            "border: none;"
            "border-radius: 0;"
            "}"
        )
        shadow_scores = QGraphicsDropShadowEffect(self.score_panel)
        shadow_scores.setBlurRadius(20)
        shadow_scores.setOffset(0, 3)
        shadow_scores.setColor(QColor(0, 0, 0, 150))
        self.lbl_scores.setGraphicsEffect(shadow_scores)
        spv.addWidget(self.lbl_scores)
        self.word_tabs_container = QWidget(self.score_panel)
        self._word_tabs_layout = QHBoxLayout(self.word_tabs_container)
        self._word_tabs_layout.setContentsMargins(0, 6, 0, 6)
        self._word_tabs_layout.setSpacing(8)
        self._word_tabs_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.word_tabs_container.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.word_tabs_container.setStyleSheet(
            """
            QPushButton {
                background-color: rgba(255, 255, 255, 0.08);
                border: 1px solid rgba(255, 255, 255, 0.25);
                border-radius: 6px;
                padding: 4px 12px;
                color: #f4f4f4;
            }
            QPushButton:checked {
                background-color: #4caf50;
                border-color: #3f9143;
                color: #0b1c00;
            }
            QPushButton:checked:hover {
                background-color: #5cc75f;
                border-color: #4caf50;
            }
            QPushButton:checked:pressed {
                background-color: #3f9143;
                border-color: #2e6f33;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.18);
            }
            """
        )
        self._word_tabs_group = QButtonGroup(self.word_tabs_container)
        self._word_tabs_group.setExclusive(True)
        self._word_tabs_group.idClicked.connect(self._on_last_move_tab_clicked)
        self._word_tab_buttons: list[QPushButton] = []
        spv.addWidget(self.word_tabs_container)
        self.word_tabs_container.hide()
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

        self.judge_subtabs_container = QWidget(self.score_panel)
        self.judge_subtabs_layout = QHBoxLayout(self.judge_subtabs_container)
        self.judge_subtabs_layout.setContentsMargins(0, 4, 0, 4)
        self.judge_subtabs_layout.setSpacing(6)
        self.judge_subtabs_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.judge_subtabs_container.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.judge_subtabs_container.setStyleSheet(
            """
            QPushButton {
                background-color: #14281b;
                border: 1px solid #2f5c39;
                border-radius: 6px;
                padding: 4px 12px;
                color: #d7f4dd;
                font-size: 12px;
                min-width: 76px;
            }
            QPushButton:hover {
                background-color: #1d3a27;
            }
            QPushButton:checked {
                background-color: #235432;
                border-color: #4caf50;
                color: #ffffff;
            }
            QPushButton:checked:hover {
                background-color: #2f6f41;
            }
            """
        )
        self._judge_subtab_group = QButtonGroup(self.judge_subtabs_container)
        self._judge_subtab_group.setExclusive(True)
        self._judge_subtab_group.idClicked.connect(self._on_judge_subtab_clicked)
        self._judge_subtab_buttons: dict[str, QPushButton] = {}
        self._judge_subtab_order: list[str] = []
        self._current_judge_detail: _WordScoreDetail | None = None
        self._current_judge_category: str | None = None
        spv.addWidget(self.judge_subtabs_container)
        self.judge_subtabs_container.hide()

        self.lbl_last_reason = QLabel("")
        self.lbl_last_reason.setWordWrap(True)
        self.lbl_last_reason.setStyleSheet(
            "QLabel{font-size:15px;color:#e8e8e8;}"
        )
        self.lbl_last_reason.hide()
        spv.addWidget(self.lbl_last_reason)
        self._clear_last_move_word_details()
        self.btn_reroll = QPushButton("Opakovať žreb")
        self.btn_reroll.clicked.connect(self._on_repeat_starter_draw)
        spv.addWidget(self.btn_reroll)
        spv.addStretch(1)
        self.btn_confirm = QPushButton("Potvrdiť ťah")
        self.btn_confirm.clicked.connect(self.confirm_move)
        self.btn_confirm.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_confirm.setMinimumHeight(40)
        self.btn_confirm.setStyleSheet(
            "QPushButton {"
            "background-color: #4caf50;"
            "color: #0b1c00;"
            "font-size: 18px;"
            "font-weight: 600;"
            "border-radius: 8px;"
            "padding: 10px 18px;"
            "}"
            "QPushButton:hover {background-color: #5cc75f;}"
            "QPushButton:pressed {background-color: #3f9143;}"
            "QPushButton:disabled {background-color: #6c7a6d;color: #dbe2dc;}"
        )
        confirm_shadow = QGraphicsDropShadowEffect(self.btn_confirm)
        confirm_shadow.setBlurRadius(20)
        confirm_shadow.setOffset(0, 3)
        confirm_shadow.setColor(QColor(0, 0, 0, 150))
        self.btn_confirm.setGraphicsEffect(confirm_shadow)
        self.btn_reroll.hide()
        self.split.addWidget(self.score_panel)
        self.split.setSizes([700, 300])
        self._stored_split_sizes: list[int] = self.split.sizes()
        self._game_ui_visible: bool = True

        # Spodný pás: rack + status
        self.rack = RackView()
        self.rack.letters_reordered.connect(self._on_rack_letters_reordered)
        self.btn_exchange = QPushButton("Vymeniť")
        self.btn_exchange.clicked.connect(self.exchange_human)
        self.btn_exchange.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        rack_bar = QWidget()
        rack_layout = QHBoxLayout(rack_bar)
        rack_layout.setContentsMargins(12, 8, 12, 8)
        rack_layout.setSpacing(12)
        rack_layout.addWidget(self.btn_exchange)
        rack_layout.addWidget(self.rack, 1)
        rack_layout.addWidget(self.btn_confirm)
        v.addWidget(rack_bar)
        self.btn_exchange.hide()
        self.rack_container = rack_bar

        # Inline settings row (timeout etc.)
        self.timeout_frame = QFrame()
        self.timeout_frame.setObjectName("timeoutFrame")
        timeout_layout = QHBoxLayout(self.timeout_frame)
        timeout_layout.setContentsMargins(18, 10, 18, 10)
        timeout_layout.setSpacing(24)

        timeout_label = QLabel("⏱ Timeout pre modely:")
        timeout_label.setStyleSheet(
            "QLabel { color: #e0e6f0; font-size: 15px; font-weight: 600; }"
        )
        timeout_layout.addWidget(timeout_label)

        self.timeout_combo = QComboBox()
        self.timeout_combo.setObjectName("timeoutCombo")
        self.timeout_combo.setStyleSheet(
            "QComboBox {"
            "background-color: #1a1a1a;"
            "color: #f0f6ff;"
            "font-size: 15px;"
            "padding: 8px 16px;"
            "border: 1px solid #2f3645;"
            "border-radius: 6px;"
            "min-width: 200px;"
            "}"
            "QComboBox::drop-down { width: 26px; border: none; }"
            "QComboBox QAbstractItemView {"
            "background: #101218; color: #f0f6ff; selection-background-color: #2d6cdf;"
            "border: 1px solid #2f3645;"
            "}"
        )
        for seconds, label in OPENROUTER_TIMEOUT_CHOICES:
            self.timeout_combo.addItem(label, seconds)

        current_timeout = self.openrouter_timeout_seconds
        current_index = self.timeout_combo.findData(current_timeout)
        if current_index == -1:
            custom_label = self._format_timeout_choice(current_timeout)
            self.timeout_combo.addItem(custom_label, current_timeout)
            current_index = self.timeout_combo.findData(current_timeout)
        self.timeout_combo.setCurrentIndex(current_index)
        self.timeout_combo.currentIndexChanged.connect(self._on_timeout_changed)
        timeout_layout.addWidget(self.timeout_combo)

        timeout_hint = QLabel("Zastaví pomalé modely po limite počas konkurenčného ťahu.")
        timeout_hint.setStyleSheet(
            "QLabel { color: #9aa5b5; font-size: 12px; }"
        )
        timeout_layout.addWidget(timeout_hint)

        self.max_tokens_label = QLabel("")
        self.max_tokens_label.setStyleSheet(
            "QLabel { color: #9aa5b5; font-size: 12px; }"
        )
        timeout_layout.addWidget(self.max_tokens_label)
        timeout_layout.addStretch(1)

        self.timeout_frame.setStyleSheet(
            "QFrame#timeoutFrame {"
            "background-color: #12141b;"
            "border-top: 1px solid #202532;"
            "border-bottom: 1px solid #202532;"
            "}"
        )

        v.addWidget(self.timeout_frame)
        self._update_max_tokens_label()

        # AI Model Results Table (below rack)
        self.model_results_table = AIModelResultsTable()
        v.addWidget(self.model_results_table)
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
        self._pass_streak: dict[str, int] = {"HUMAN": 0, "AI": 0}
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
        self._exchange_mode_active: bool = False
        self._starter_side: StarterSide | None = None
        self._starter_decided: bool = False

        self._reset_to_idle_state()

    def _load_openrouter_timeout(self) -> int:
        raw = os.getenv("OPENROUTER_TIMEOUT_SECONDS")
        try:
            value = int(raw) if raw is not None else DEFAULT_OPENROUTER_TIMEOUT
        except ValueError:
            value = DEFAULT_OPENROUTER_TIMEOUT
        if value < 5:
            value = DEFAULT_OPENROUTER_TIMEOUT
        return value

    @staticmethod
    def _load_ai_move_max_tokens() -> tuple[int, bool]:
        raw = os.getenv("AI_MOVE_MAX_OUTPUT_TOKENS")
        default = 3600
        if raw is None:
            return default, False
        try:
            value = int(raw)
        except ValueError:
            return default, False
        if value <= 0:
            return default, False
        return value, True

    def _update_max_tokens_label(self) -> None:
        if hasattr(self, "max_tokens_label") and self.max_tokens_label is not None:
            self.max_tokens_label.setText("Maximálne tokenov na ťah:")
            self.max_tokens_label.setToolTip(
                f"Aktuálny limit: {self.ai_move_max_tokens} tokenov"
            )

    @staticmethod
    def _format_timeout_choice(seconds: int) -> str:
        if seconds % 60 == 0:
            minutes = seconds // 60
            if minutes == 1:
                return "1 minúta"
            if minutes in {2, 3, 4}:
                return f"{minutes} minúty"
            return f"{minutes} minút"
        return f"{seconds} sekúnd"

    def _update_env_value(self, key: str, value: str) -> None:
        os.environ[key] = value
        try:
            from dotenv import set_key as _set_key  # type: ignore
            _set_key(ENV_PATH, key, value)
        except Exception:
            self._write_env_value_manually(key, value)

    def _write_env_value_manually(self, key: str, value: str) -> None:
        try:
            path = Path(ENV_PATH)
            if not path.exists():
                path.touch()
            lines = path.read_text(encoding="utf-8").splitlines()
            updated = False
            new_lines: list[str] = []
            for line in lines:
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    new_lines.append(line)
                    continue
                if stripped.split("=", 1)[0].strip() == key:
                    new_lines.append(f"{key}='{value}'")
                    updated = True
                else:
                    new_lines.append(line)
            if not updated:
                new_lines.append(f"{key}='{value}'")
            path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        except Exception:
            log.exception("Failed to persist %s to .env", key)

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
            for key, value in resp.items():
                if isinstance(value, dict) and ("valid" in value or "reason" in value or "word" in value):
                    word = value.get("word") if isinstance(value.get("word"), str) else None
                    if word is None and isinstance(key, str):
                        word = key
                    normalized = dict(value)
                    if word is not None:
                        normalized["word"] = word
                    if word is not None and any(entry.get("word") == word for entry in entries):
                        continue
                    entries.append(normalized)
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
        self._exit_exchange_mode()
        
        # Mark game as in progress
        self.game_in_progress = True
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
        self._last_move_reason = ""
        self._last_move_reason_is_html = False
        self._clear_last_move_word_details()
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
        show_reroll = (not decided) and self._game_ui_visible
        self.btn_reroll.setVisible(show_reroll)
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

    def _on_timeout_changed(self, index: int) -> None:
        if index < 0:
            return
        data = self.timeout_combo.itemData(index)
        try:
            seconds = int(data)
        except (TypeError, ValueError):
            return
        if seconds == self.openrouter_timeout_seconds:
            return
        self.openrouter_timeout_seconds = seconds
        self._update_env_value("OPENROUTER_TIMEOUT_SECONDS", str(seconds))
        display = self._format_timeout_choice(seconds)
        log.info("Timeout updated to %s (%ds)", display, seconds)
        if hasattr(self, "status") and isinstance(self.status, QStatusBar):
            self.status.showMessage(f"Timeout nastavený na {display}", 4000)

    def _reset_to_idle_state(self) -> None:
        """Vráti aplikáciu do východzieho stavu pred spustením hry."""
        # zastav animácie/spinner a ukonči rozbehnuté vlákna
        self._clear_spinner_state()
        self._exit_exchange_mode()
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
        self._last_move_reason = ""
        self._last_move_reason_is_html = False
        self._clear_last_move_word_details()
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
        self._set_starter_controls(decided=False)

    def _update_scores_label(self) -> None:
        self.lbl_scores.setText(
            f"<div>Hráč: <b>{self.human_score}</b> vs. AI: <b>{self.ai_score}</b></div>"
        )
        self._update_last_move_breakdown_ui()
        self._update_last_move_reason_ui()

    def _update_last_move_breakdown_ui(self) -> None:
        """Aktualizuje panel rozpisu 'Posledný ťah'."""
        if not self._last_move_word_details or self._active_word_index is None:
            self.lbl_last_breakdown.setText("")
            self.word_tabs_container.hide()
            return
        count = len(self._last_move_word_details)
        if not (0 <= self._active_word_index < count):
            self._active_word_index = 0
        detail = self._last_move_word_details[self._active_word_index]
        self.word_tabs_container.show()
        line = (
            f"{detail.base_points}, písmená +{detail.letter_bonus_points}, "
            f"násobok ×{detail.word_multiplier} → "
            f"<span style='font-weight:bold'>{detail.total}</span>"
        )
        lines = [line]
        if self._last_move_bingo:
            lines.append("<span style='color:#9cff9c'>+50 bingo!</span>")
        html_lines = "<br/>".join(lines)
        self.lbl_last_breakdown.setText(f"<div style='margin-bottom:6px'>{html_lines}</div>")

    def _rebuild_last_move_word_tabs(self) -> None:
        while self._word_tabs_layout.count():
            item = self._word_tabs_layout.takeAt(0)
            widget = item.widget()
            if isinstance(widget, QAbstractButton):
                self._word_tabs_group.removeButton(widget)
            if widget is not None:
                widget.deleteLater()
        self._word_tab_buttons.clear()
        if not self._last_move_word_details:
            self.word_tabs_container.hide()
            return
        for idx, detail in enumerate(self._last_move_word_details):
            btn = QPushButton(detail.word, self.word_tabs_container)
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self._word_tabs_layout.addWidget(btn)
            self._word_tabs_group.addButton(btn, idx)
            self._word_tab_buttons.append(btn)
        self._word_tabs_layout.addStretch(1)
        self.word_tabs_container.show()

    def _clear_judge_subtabs(self) -> None:
        for btn in list(self._judge_subtab_group.buttons()):
            self._judge_subtab_group.removeButton(btn)
        while self.judge_subtabs_layout.count():
            item = self.judge_subtabs_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._judge_subtab_buttons.clear()
        self._judge_subtab_order.clear()
        self.judge_subtabs_container.hide()
        self._current_judge_category = None
        self._current_judge_detail = None

    def _refresh_judge_subtabs(self, detail: _WordScoreDetail) -> None:
        categories: list[tuple[str, str]] = []
        if detail.reason:
            categories.append(("reason", "Dôvod"))
        if detail.lexicons:
            categories.append(("lexicons", "Lexikóny"))
        if detail.definitions:
            categories.append(("definitions", "Definície"))
        if detail.examples:
            categories.append(("examples", "Príklady"))
        if detail.notes:
            categories.append(("notes", "Poznámky"))

        self._clear_judge_subtabs()
        self._current_judge_detail = detail

        if not categories:
            self._set_last_move_reason("")
            return

        for idx, (key, label) in enumerate(categories):
            btn = QPushButton(label, self.judge_subtabs_container)
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setProperty("judge_category", key)
            self.judge_subtabs_layout.addWidget(btn)
            self._judge_subtab_group.addButton(btn, idx)
            self._judge_subtab_buttons[key] = btn
            self._judge_subtab_order.append(key)

        self.judge_subtabs_layout.addStretch(1)
        self.judge_subtabs_container.show()

        first_key = self._judge_subtab_order[0]
        btn = self._judge_subtab_buttons[first_key]
        btn.setChecked(True)
        self._apply_judge_subtab_selection(first_key)

    def _on_judge_subtab_clicked(self, tab_id: int) -> None:
        btn = self._judge_subtab_group.button(tab_id)
        if btn is None:
            return
        category = btn.property("judge_category")
        if isinstance(category, str):
            self._apply_judge_subtab_selection(category)

    def _apply_judge_subtab_selection(self, category: str) -> None:
        detail = self._current_judge_detail
        if detail is None:
            self._set_last_move_reason("")
            return
        self._current_judge_category = category
        content = self._render_judge_subtab_content(detail, category)
        if content:
            self._set_last_move_reason(content, is_html=True)
        else:
            self._set_last_move_reason("")

    @staticmethod
    def _render_list_html(items: tuple[str, ...]) -> str:
        list_items = "".join(f"<li>{html.escape(text)}</li>" for text in items if text)
        if not list_items:
            return ""
        return (
            "<ul style='margin:6px 0 0 18px; padding:0 0 0 4px; line-height:1.4;'>"
            f"{list_items}</ul>"
        )

    def _render_judge_subtab_content(self, detail: _WordScoreDetail, category: str) -> str:
        labels = {
            "reason": "Dôvod",
            "lexicons": "Lexikóny",
            "definitions": "Definície",
            "examples": "Príklady",
            "notes": "Poznámky",
        }
        label = labels.get(category, "")
        title = html.escape(detail.word)
        if label:
            header = (
                "<div style='font-weight:bold;margin-bottom:4px'>"
                f"{title} — {html.escape(label)}</div>"
            )
        else:
            header = f"<div style='font-weight:bold;margin-bottom:4px'>{title}</div>"
        if category == "reason":
            if not detail.reason:
                return ""
            body = html.escape(detail.reason).replace("\n", "<br/>")
            return header + f"<div style='line-height:1.4'>{body}</div>"
        if category == "lexicons":
            body = self._render_list_html(detail.lexicons)
            return header + body
        if category == "definitions":
            body = self._render_list_html(detail.definitions)
            return header + body
        if category == "examples":
            body = self._render_list_html(detail.examples)
            return header + body
        if category == "notes":
            if not detail.notes:
                return ""
            body = html.escape(detail.notes).replace("\n", "<br/>")
            return header + f"<div style='line-height:1.4'>{body}</div>"
        return ""

    def _select_last_move_word(self, index: int) -> None:
        if not self._last_move_word_details:
            self._active_word_index = None
            self.lbl_last_breakdown.setText("")
            self.word_tabs_container.hide()
            self._clear_judge_subtabs()
            self._set_last_move_reason("")
            return
        index = max(0, min(index, len(self._last_move_word_details) - 1))
        self._active_word_index = index
        try:
            self._word_tabs_group.blockSignals(True)
            for idx, btn in enumerate(self._word_tab_buttons):
                btn.setChecked(idx == index)
        finally:
            self._word_tabs_group.blockSignals(False)
        detail = self._last_move_word_details[index]
        self._refresh_judge_subtabs(detail)
        self._update_last_move_breakdown_ui()

    def _on_last_move_tab_clicked(self, index: int) -> None:
        self._select_last_move_word(index)

    def _clear_last_move_word_details(self) -> None:
        self._last_move_word_details = []
        self._active_word_index = None
        self._rebuild_last_move_word_tabs()
        self.lbl_last_breakdown.setText("")
        self._clear_judge_subtabs()

    def _update_last_move_reason_ui(self) -> None:
        """Zobrazí alebo schová dôvod rozhodcu pre posledný platný ťah."""
        reason = self._last_move_reason.strip()
        if not reason:
            self.lbl_last_reason.hide()
            self.lbl_last_reason.setText("")
            return
        if self._last_move_reason_is_html:
            escaped = reason
        else:
            escaped = html.escape(reason).replace("\n", "<br/>")
        self.lbl_last_reason.setText(
            "<div style='margin:6px 0 0 0'>"
            f"{escaped}</div>"
        )
        self.lbl_last_reason.show()

    def _set_last_move_reason(self, reason: str, *, is_html: bool = False) -> None:
        """Uloží dôvod rozhodcu k poslednému platnému ťahu a refreshne UI."""
        stripped = reason.strip()
        self._last_move_reason = stripped
        self._last_move_reason_is_html = bool(is_html and stripped)
        self._update_last_move_reason_ui()

    @staticmethod
    def _extract_reason_from_entries(
        entries: list[dict[str, Any]],
        preferred_word: str | None = None,
    ) -> str:
        """Vyberie najrelevantnejší dôvod z odpovede rozhodcu."""
        preferred_cf = preferred_word.casefold() if preferred_word else None
        fallback_reason = ""
        for entry in entries:
            if not bool(entry.get("valid", False)):
                continue
            reason = str(entry.get("reason", "")).strip()
            if not reason:
                continue
            word = str(entry.get("word", ""))
            if preferred_cf and word.casefold() == preferred_cf:
                return reason
            if not fallback_reason:
                fallback_reason = reason
        return fallback_reason

    @staticmethod
    def _build_reason_lookup(entries: Sequence[dict[str, Any]]) -> dict[str, str]:
        lookup: dict[str, str] = {}
        for entry in entries:
            word = str(entry.get("word", "")).strip()
            if not word:
                continue
            reason = str(entry.get("reason", "")).strip()
            if reason:
                lookup[word.casefold()] = reason
        return lookup

    def _compose_last_move_word_details(
        self,
        breakdown: Sequence[tuple[str, int, int, int, int]],
        entries: Sequence[dict[str, Any]],
        preferred_word: str,
        fallback_reason: str,
    ) -> list[_WordScoreDetail]:
        lookup = self._build_reason_lookup(entries)
        preferred_cf = preferred_word.casefold() if preferred_word else None
        entry_lookup: dict[str, dict[str, Any]] = {}

        def _score_entry(payload: dict[str, Any]) -> int:
            score = 0
            for list_field in ("lexicons", "definitions", "examples"):
                value = payload.get(list_field)
                if isinstance(value, (list, tuple)):
                    score += len(value)
                elif isinstance(value, str) and value.strip():
                    score += 1
            notes_value = payload.get("notes")
            if isinstance(notes_value, str) and notes_value.strip():
                score += 1
            reason_value = payload.get("reason")
            if isinstance(reason_value, str) and reason_value.strip():
                score += 1
            return score

        for entry in entries:
            word_value = entry.get("word")
            if isinstance(word_value, str) and word_value.strip():
                key = word_value.strip().casefold()
                existing = entry_lookup.get(key)
                if existing is None or _score_entry(entry) >= _score_entry(existing):
                    entry_lookup[key] = entry
        details: list[_WordScoreDetail] = []
        for idx, (word, base, letter_bonus, word_multiplier, total) in enumerate(breakdown):
            reason = lookup.get(word.casefold(), "")
            if not reason:
                if preferred_cf and word.casefold() == preferred_cf and fallback_reason:
                    reason = fallback_reason
                elif not preferred_cf and idx == 0 and fallback_reason:
                    reason = fallback_reason
            entry_data = entry_lookup.get(word.casefold(), {})
            def _coerce_list(field_name: str) -> tuple[str, ...]:
                value = entry_data.get(field_name)
                if isinstance(value, (list, tuple)):
                    collected = [str(item).strip() for item in value if str(item).strip()]
                    return tuple(collected)
                if isinstance(value, str) and value.strip():
                    return (value.strip(),)
                return tuple()
            lexicons = _coerce_list("lexicons")
            definitions = _coerce_list("definitions")
            examples = _coerce_list("examples")
            notes_val = entry_data.get("notes")
            notes = str(notes_val).strip() if isinstance(notes_val, str) else ""
            details.append(
                _WordScoreDetail(
                    word=word,
                    base_points=base,
                    letter_bonus_points=letter_bonus,
                    word_multiplier=word_multiplier,
                    total=total,
                    reason=reason,
                    lexicons=lexicons,
                    definitions=definitions,
                    examples=examples,
                    notes=notes,
                )
            )
        return details

    def _format_judge_status(self, words: list[str]) -> str:
        """Format judge status message with model name if available."""
        model_name = getattr(self, '_current_ai_model', None)
        model_prefix = f"[{model_name}] " if model_name and model_name != "AI" else ""
        
        if not words:
            return f"{model_prefix}Rozhoduje rozhodca"
        if len(words) == 1:
            return f"{model_prefix}Rozhodca rozhoduje slovo {words[0]}"
        joined = ", ".join(words)
        return f"{model_prefix}Rozhodca rozhoduje slová: {joined}"

    def _append_pending_tile(self, placement: Placement) -> None:
        """Pridá dočasne položené písmeno a refreshne UI."""
        self.pending.append(placement)
        self.board_view.set_pending(self.pending)
        self.board_view.flash_cell(placement.row, placement.col)
        self._update_ghost_score()

    def _handle_tile_drop(self, row: int, col: int, payload: dict[str, Any]) -> bool:
        origin = payload.get("origin")
        if origin == "rack":
            return self._place_tile_from_rack(row, col, payload)
        if origin == "board":
            return self._reposition_pending_tile(row, col, payload)
        return False

    def _place_tile_from_rack(self, row: int, col: int, payload: dict[str, Any]) -> bool:
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

    def _reposition_pending_tile(self, row: int, col: int, payload: dict[str, Any]) -> bool:
        original_row = int(payload.get("row", -1))
        original_col = int(payload.get("col", -1))
        if original_row == -1 or original_col == -1:
            return False
        if row == original_row and col == original_col:
            return True
        if self.board.cells[row][col].letter:
            self.status.showMessage("Pole je obsadené.", 2000)
            return False
        for placement in self.pending:
            if placement.row == row and placement.col == col:
                self.status.showMessage("Pole už obsahuje dočasné písmeno.", 2000)
                return False
        target_index: Optional[int] = None
        original_placement: Optional[Placement] = None
        for idx, placement in enumerate(self.pending):
            if placement.row == original_row and placement.col == original_col:
                target_index = idx
                original_placement = placement
                break
        if target_index is None or original_placement is None:
            return False
        updated = Placement(
            row=row,
            col=col,
            letter=original_placement.letter,
            blank_as=original_placement.blank_as,
        )
        self.pending[target_index] = updated
        self.board_view.set_pending(self.pending)
        self.board_view.flash_cell(row, col)
        self._update_ghost_score()
        return True

    def _handle_pending_drag_finished(self, payload: dict[str, Any], action: Qt.DropAction) -> None:
        if action != Qt.DropAction.MoveAction:
            return
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

    def _on_rack_letters_reordered(self, letters: list[str]) -> None:
        """Synchronizuje interný poradie písmen po drag-and-drop zmene."""
        self.human_rack = list(letters)

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
        self.status.showMessage(f"Potencionálne skóre: {score}")

    def _refresh_board_view(self) -> None:
        """Zabezpečí prekreslenie dosky po manuálnych zmenách stavu."""
        self.board_view.update()

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

    def _parse_blank_map(
        self, blanks_obj: object
    ) -> tuple[dict[tuple[int, int], str], Optional[str]]:
        """Normalizuje mapovanie blankov zo schémy AI na interný formát."""

        blank_map: dict[tuple[int, int], str] = {}
        if blanks_obj is None:
            return blank_map, None
        if isinstance(blanks_obj, dict):
            try:
                for key, value in blanks_obj.items():
                    if not isinstance(key, str):
                        return {}, "Blanks položky majú zlý formát."
                    row_str, col_str = (part.strip() for part in key.split(",", 1))
                    row = int(row_str)
                    col = int(col_str)
                    blank_map[(row, col)] = str(value)
            except Exception:
                return {}, "Blanks položky majú zlý formát."
            return blank_map, None
        if isinstance(blanks_obj, list):
            try:
                for item in blanks_obj:
                    if not ("row" in item and "col" in item and "as" in item):
                        return {}, "Blanks položky majú zlý formát."
                    row = int(item["row"])
                    col = int(item["col"])
                    blank_map[(row, col)] = str(item["as"])
            except Exception:
                return {}, "Blanks položky majú zlý formát."
            return blank_map, None
        if blanks_obj in ({}, []):
            return blank_map, None
        return {}, "Blanks položky majú zlý formát."

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

    def _handle_invalid_turn(self, word: str, reason: str) -> None:
        """Vráti stav hry pri zamietnutom ťahu a ukáže používateľovi dôvod."""
        self.board.clear_letters(self.pending)
        self.human_rack = restore_rack(self.human_rack, self.pending)
        self.pending = []
        self.rack.set_letters(self.human_rack)
        self.board_view.set_pending(self.pending)
        self._pending_words_coords = []
        self.status.showMessage("Hrá hráč…")
        msg = "Neplatný ťah"
        if word:
            msg = f"Neplatné slovo: {word}"
        if reason:
            msg = f"{msg}\nDôvod: {reason}"
        QMessageBox.information(self, "Neplatný ťah", msg)

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
        self._refresh_board_view()
        words_found = extract_all_words(self.board, self.pending)
        words_coords = [(wf.word, wf.letters) for wf in words_found]
        words = [wf.word for wf in words_found]
        log.info("Rozhodca overuje slová: %s", words)
        # spusti spinner (online judge)
        judge_status = self._format_judge_status(words)
        self._start_status_spinner("judge", judge_status, wait_cursor=False)

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
            invalid_entries = [it for it in entries if not bool(it.get("valid", False))]
            if invalid_entries:
                primary = invalid_entries[0]
                bad_word = str(primary.get("word", ""))
                bad_reason = str(primary.get("reason", ""))
                self._handle_invalid_turn(bad_word, bad_reason)
                return
            else:
                self._handle_invalid_turn("", "")
                return

        # validne: spocitaj skore + bingo, aplikuj prémie a dopln rack
        words_coords = getattr(self, "_pending_words_coords")
        main_word = ""
        if words_coords:
            main_word = max(words_coords, key=lambda item: len(item[0]))[0]
        reason_text = self._extract_reason_from_entries(entries, main_word)
        total, _bd = score_words(self.board, self.pending, words_coords)
        # uloz rozpis pre UI
        self._last_move_breakdown = [(bd.word, bd.base_points, bd.letter_bonus_points, bd.word_multiplier, bd.total) for bd in _bd]
        self._last_move_word_details = self._compose_last_move_word_details(
            self._last_move_breakdown,
            entries,
            main_word,
            reason_text,
        )
        self._rebuild_last_move_word_tabs()
        if self._last_move_word_details:
            self._select_last_move_word(0)
        else:
            self._active_word_index = None
            self._set_last_move_reason(reason_text)
            self._update_last_move_breakdown_ui()
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
        # Rack už v tomto momente neobsahuje dočasne položené kamene –
        # odobrali sme ich pri interakcii hráča (drag alebo klik z racku).
        # Opätovné volanie `consume_rack` by preto odstránilo aj iné blanky,
        # ktoré na racku zostali. Pracujeme teda priamo s aktuálnym stavom.
        new_rack = list(self.human_rack)
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
        # vráť dosku do stavu pred potvrdením a pridaj písmená späť na rack
        self.board.clear_letters(self.pending)
        self.human_rack = restore_rack(self.human_rack, self.pending)
        self.pending = []
        self._pending_words_coords = []
        self.rack.set_letters(self.human_rack)
        self.board_view.set_pending(self.pending)
        self.status.showMessage("Hrá hráč…")
        QMessageBox.critical(self, "Chyba rozhodcu", str(e))

    # ---------- AI tah ----------
    def _disable_human_inputs(self) -> None:
        self._exit_exchange_mode()
        self.btn_confirm.setEnabled(False)
        self.board_view.setEnabled(False)
        self.rack.setEnabled(False)
        self.btn_exchange.setEnabled(False)

    def _enable_human_inputs(self) -> None:
        self.btn_confirm.setEnabled(True)
        self.board_view.setEnabled(True)
        self.rack.setEnabled(True)
        self.btn_exchange.setEnabled(True)

    def _enter_exchange_mode(self) -> None:
        if self._exchange_mode_active:
            return
        self._exchange_mode_active = True
        self.btn_exchange.setText("Potvrdiť")
        self.rack.set_multi_selection_enabled(True)
        self.status.showMessage("Vyber kamene na výmenu a klikni na Potvrdiť.")

    def _exit_exchange_mode(self, *, status_message: str | None = None) -> None:
        if not self._exchange_mode_active:
            return
        self._exchange_mode_active = False
        self.btn_exchange.setText("Vymeniť písmená")
        self.rack.set_multi_selection_enabled(False)
        if status_message is not None:
            self.status.showMessage(status_message)
        elif not self._ai_thinking:
            self.status.showMessage("Hrá hráč…")

    def exchange_human(self) -> None:
        """Spracovanie akcie na tlačidle výmeny kameňov."""
        if self._ai_thinking:
            return
        if not self._exchange_mode_active:
            if self.bag.remaining() < 7:
                QMessageBox.information(
                    self,
                    "Vymeniť",
                    "Taška má menej ako 7 kameňov – výmena nie je povolená.",
                )
                return
            self._enter_exchange_mode()
            return

        # potvrdzujeme výmenu
        selected_items = self.rack.list.selectedItems()
        selected: list[str] = [it.text() for it in selected_items]
        if not selected:
            log.info("[HUMAN] exchange cancelled (no selection)")
            self._exit_exchange_mode(status_message="Výmena zrušená.")
            return

        TRACE_ID_VAR.set(str(uuid.uuid4())[:8])
        log.info("[HUMAN] confirm exchange letters=%s", "".join(selected))

        tmp_rack = self.human_rack.copy()
        for ch in selected:
            if ch in tmp_rack:
                tmp_rack.remove(ch)
                continue
            QMessageBox.warning(self, "Vymeniť", "Vybraný kameň sa nenašiel v racku.")
            self._exit_exchange_mode()
            return

        self.status.showMessage("Hráč vymieňa…")
        new_tiles = self.bag.exchange(selected)
        self.human_rack = tmp_rack + new_tiles
        self._exit_exchange_mode()
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
        self._start_status_spinner("ai", "Hrá AI", wait_cursor=False)
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
            multi_model_results: Signal = Signal(list)
            partial_result: Signal = Signal(dict)
            def __init__(
                self,
                client: OpenAIClient,
                state_str: str,
                trace_id: str,
                variant: VariantDefinition,
                use_multi_model: bool,
                selected_models: list[dict[str, Any]],
                board: Board,
                timeout_seconds: int,
            ) -> None:
                super().__init__()
                self.client = client
                self.state_str = state_str
                self.trace_id = trace_id
                self.variant = variant
                self.use_multi_model = use_multi_model
                self.selected_models = selected_models
                self.board = board
                self.timeout_seconds = timeout_seconds
            def run(self) -> None:
                try:
                    TRACE_ID_VAR.set(self.trace_id)
                    if self.use_multi_model and self.selected_models:
                        import asyncio
                        import os
                        api_key = os.getenv("OPENROUTER_API_KEY", "")
                        openrouter_client = OpenRouterClient(
                            api_key,
                            timeout_seconds=self.timeout_seconds,
                        )
                        
                        async def run_multi() -> tuple[dict[str, Any], list[dict[str, Any]]]:
                            def on_partial(res: dict[str, Any]) -> None:
                                self.partial_result.emit(res)

                            try:
                                move, results = await propose_move_multi_model(
                                    openrouter_client,
                                    self.selected_models,
                                    self.state_str,
                                    self.variant,
                                    self.board,
                                    self.client,
                                    progress_callback=on_partial,
                                    timeout_seconds=self.timeout_seconds,
                                )
                            finally:
                                await openrouter_client.close()

                            log.info(
                                "Multi-model: %d models, best score from %s",
                                len(results),
                                next(
                                    (
                                        r.get("model_name")
                                        for r in results
                                        if r.get("status") == "ok"
                                    ),
                                    "?",
                                ),
                            )
                            return move, results
                        
                        resp, results = asyncio.run(run_multi())
                        self.multi_model_results.emit(results)
                    else:
                        resp = ai_propose_move(
                            client=self.client,
                            compact_state=self.state_str,
                            variant=self.variant,
                        )
                    self.finished.emit(resp)
                except Exception as e:  # noqa: BLE001
                    self.failed.emit(e)

        self._ai_thread = QThread(self)
        self._ai_worker = ProposeWorker(
            self.ai_client,
            compact,
            TRACE_ID_VAR.get(),
            self.variant_definition,
            self.use_multi_model,
            self.selected_ai_models,
            self.board,
            self.openrouter_timeout_seconds,
        )

        if self.use_multi_model and self.selected_ai_models:
            self.model_results_table.initialize_models(self.selected_ai_models)
        else:
            self.model_results_table.clear_results()

        self._ai_worker.moveToThread(self._ai_thread)
        self._ai_thread.started.connect(self._ai_worker.run)
        # Connect signals - results come first, then proposal
        self._ai_worker.multi_model_results.connect(self._on_multi_model_results)
        self._ai_worker.partial_result.connect(self._on_multi_model_partial)
        self._ai_worker.finished.connect(self._on_ai_proposal)
        self._ai_worker.failed.connect(self._on_ai_fail)
        self._ai_worker.finished.connect(self._ai_thread.quit)
        self._ai_worker.failed.connect(self._ai_thread.quit)
        self._ai_thread.start()
        
        # Update status to show models are being called
        if self.use_multi_model and self.selected_ai_models:
            model_count = len(self.selected_ai_models)
            model_names = ", ".join(
                [m.get("name", m.get("id", "?"))[:20] for m in self.selected_ai_models[:3]]
            )
            if model_count > 3:
                model_names += f" +{model_count - 3} ďalších"
            self.status.showMessage(f"Volám {model_count} modelov: {model_names}...")
    
    def _on_multi_model_partial(self, result: dict[str, Any]) -> None:
        """Handle incremental model result updates."""
        model_id = result.get("model", "?")
        model_name = result.get("model_name", model_id)
        status = result.get("status", "pending")
        score = result.get("score")

        log.info(
            "Partial result from %s status=%s score=%s", model_name, status, score
        )

        self.model_results_table.update_result(result)

        if status == "ok":
            words = result.get("words") or []
            word_preview = ", ".join(words) if words else result.get("move", {}).get("word", "—")
            score_text = f"{score} b" if isinstance(score, (int, float)) else "—"
            self.status.showMessage(
                f"{model_name} odpovedal: {word_preview} ({score_text})"
            )
        elif status == "parse_error":
            self.status.showMessage(f"{model_name}: neplatná odpoveď – čakám na ostatné modely")
        elif status == "error":
            self.status.showMessage(f"{model_name}: API chyba – čakám na ostatné modely")
        elif status == "timeout":
            self.status.showMessage(f"{model_name}: Timeout – čakám na ostatné modely")

    def _on_multi_model_results(self, results: list[dict[str, Any]]) -> None:
        """Handle multi-model competition results and display in table."""
        log.info("Received multi-model results: %d models", len(results))
        
        # Update table immediately with results
        self.model_results_table.set_results(results)
        
        # Store the winning model name for status messages
        # Find the best valid result
        valid_results = [r for r in results if r.get("judge_valid")]
        if valid_results:
            valid_results.sort(key=lambda r: int(r.get("score", -1)), reverse=True)
            self._current_ai_model = valid_results[0].get("model_name", "AI")
            winner_word = ", ".join(valid_results[0].get("words", []))
            winner_score = valid_results[0].get("score", 0)
            self.status.showMessage(
                f"✓ Víťaz: {self._current_ai_model} - {winner_word} ({winner_score} bodov)"
            )
        else:
            # No valid results, find highest scoring attempt
            all_sorted = sorted(results, key=lambda r: int(r.get("score", -1)), reverse=True)
            if all_sorted:
                self._current_ai_model = all_sorted[0].get("model_name", "AI")
                self.status.showMessage(f"⚠️ Žiadne platné návrhy, používam {self._current_ai_model}")
            else:
                self._current_ai_model = "AI"
                self.status.showMessage("⚠️ Žiadne platné návrhy od modelov")
    
    def _update_table_for_judging(self, words: list[str]) -> None:
        """Update table to highlight which words are being judged."""
        model_name = getattr(self, '_current_ai_model', "AI")
        log.info("Judge validating words %s from model %s", words, model_name)
        
        # Update status message to show which model's move is being judged
        words_str = ", ".join(words)
        judge_status = f"Rozhodca validuje: {words_str} (navrhol {model_name})"
        self.status.showMessage(judge_status)

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
            ps: list[Placement] = []
            for p in placements_list:
                if not isinstance(p, dict):
                    return "Placement nie je dict."
                if "row" not in p or "col" not in p or "letter" not in p:
                    return f"Placement chýbajú kľúče (row/col/letter): {p}"
                ps.append(Placement(int(p["row"]), int(p["col"]), str(p["letter"])))
        except (KeyError, ValueError, TypeError) as e:
            return f"Placements nemajú správny tvar: {e}"
        # nesmie prepisovať existujúce písmená
        for p in ps:
            if self.board.cells[p.row][p.col].letter:
                return "AI sa pokúsila položiť na obsadené pole."
        dir_ = placements_in_line(ps)
        if dir_ is None:
            return "AI ťah nie je v jednej línii."
        # dopln blank_as z response ak je
        blanks = proposal.get("blanks")
        blank_map, blank_err = self._parse_blank_map(blanks)
        if blank_err is not None:
            return blank_err
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
        # validacia - bez retry, jednoducho pass pri chybe
        err = self._validate_ai_move(proposal)
        if err is not None and not bool(proposal.get("pass", False)):
            # Neplatný návrh - AI pasuje bez retry
            model_name = getattr(self, '_current_ai_model', "AI")
            self.status.showMessage(f"[{model_name}] Neplatný návrh ({err}), AI pasuje")
            log.warning("AI navrhol neplatný ťah: %s", err)
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
        ps: list[Placement] = []
        for p in placements_list:
            if not isinstance(p, dict) or "row" not in p or "col" not in p or "letter" not in p:
                log.error("Invalid placement dict: %s", p)
                self.status.showMessage("AI vrátila neplatný placement")
                self._stop_status_spinner("ai")
                self._ai_thinking = False
                self._enable_human_inputs()
                self._register_scoreless_turn("AI")
                return
            ps.append(Placement(int(p["row"]), int(p["col"]), str(p["letter"])))
        blanks = proposal.get("blanks")
        blank_map, _ = self._parse_blank_map(blanks)
        # nastav blank_as; ak AI oznacila v `blanks`, prekonvertuj na '?'
        ps2: list[Placement] = []
        for p in ps:
            if (p.row, p.col) in blank_map:
                ps2.append(Placement(p.row, p.col, "?", blank_as=blank_map[(p.row,p.col)]))
            else:
                ps2.append(p)
        self.board.place_letters(ps2)
        self._refresh_board_view()
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
            # Neplatné - AI pasuje bez retry
            self.board.clear_letters(ps2)
            self._refresh_board_view()
            log.warning("AI vytvorila neplatné lepené slovo: main=%s anchor=%s", main_word, anchor)
            self._stop_status_spinner("ai")
            self._ai_thinking = False
            self._enable_human_inputs()
            self.status.showMessage(f"AI vytvorila neplatné lepené slovo '{main_word}' — pasuje")
            self._register_scoreless_turn("AI")
            if self._ai_opening_active:
                try:
                    log.info("ai_opening done result=invalid_glued_word")
                except Exception:
                    pass
                self._ai_opening_active = False
            self._check_endgame()
            return

        # For retry success, show in table
        if self._ai_retry_used and hasattr(self, '_current_ai_model'):
            # Create a single-row result for the successful retry
            retry_result = {
                "model": "gpt-5-mini",
                "model_name": self._current_ai_model,
                "status": "ok",
                "move": {"word": words[0] if words else ""},
                "score": 0,  # Will be calculated by judge
                "words": words,
                "judge_valid": None,  # Will be set after judge
            }
            self.model_results_table.set_results([retry_result])
        
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
        judge_status = self._format_judge_status(words)
        self._start_status_spinner("judge", judge_status, wait_cursor=False)
        
        # Update table to show which words are being judged
        self._update_table_for_judging(words)
        
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
                self._refresh_board_view()
                self._ai_retry_used = True
                invalid_word = ""
                invalid_reason = ""
                for it in entries:
                    if not bool(it.get("valid", False)):
                        invalid_word = str(it.get("word", ""))
                        invalid_reason = str(it.get("reason", ""))
                        break
                # Judge rejected move - AI pasuje bez retry
                summary_word = invalid_word or self._ai_last_main_word or ""
                summary_reason = invalid_reason or self._ai_last_anchor or ""
                log.warning(
                    "Judge zamietol AI ťah: word=%s reason=%s",
                    summary_word,
                    summary_reason,
                )
            # inak: pass
            self.board.clear_letters(getattr(self, "_ai_ps2"))
            self._refresh_board_view()
            self._ai_thinking = False
            self._enable_human_inputs()
            self.status.showMessage("AI navrhla neplatné slovo — pass")
            self._register_scoreless_turn("AI")
            self._check_endgame()
            return
        # validne: spocitaj, aplikuj prémie, refill
        words_coords = self._ai_judge_words_coords
        ps2 = self._ai_ps2
        reason_text = self._extract_reason_from_entries(entries, self._ai_last_main_word or "")
        total, _bd = score_words(self.board, ps2, words_coords)
        # rozpis pre UI (posledny tah = AI tah)
        self._last_move_breakdown = [(bd.word, bd.base_points, bd.letter_bonus_points, bd.word_multiplier, bd.total) for bd in _bd]
        self._last_move_word_details = self._compose_last_move_word_details(
            self._last_move_breakdown,
            entries,
            self._ai_last_main_word or "",
            reason_text,
        )
        self._rebuild_last_move_word_tabs()
        if self._last_move_word_details:
            self._select_last_move_word(0)
        else:
            self._active_word_index = None
            self._set_last_move_reason(reason_text)
            self._update_last_move_breakdown_ui()
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
        self._refresh_board_view()
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

        # Mark game as no longer in progress
        self.game_in_progress = False
        
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
        from .settings_dialog import SettingsDialog as UnifiedSettingsDialog
        
        dlg = UnifiedSettingsDialog(
            self,
            current_mode=self.opponent_mode,
            current_agent_name=self.selected_agent_name,
            available_agents=self.available_agents,
            game_in_progress=self.game_in_progress,
            ai_move_max_tokens=self.ai_move_max_tokens,
            ai_tokens_from_env=self._ai_tokens_from_env,
            user_defined_ai_tokens=self._user_defined_ai_tokens,
            repro_mode=self.repro_mode,
            repro_seed=self.repro_seed,
            active_tab_index=0,  # Open General tab (default, most important settings)
        )
        ok = dlg.exec()
        if ok:
            new_ai_tokens, from_env = self._load_ai_move_max_tokens()
            self.ai_move_max_tokens = new_ai_tokens
            self._ai_tokens_from_env = from_env
            self._user_defined_ai_tokens = False
            self._update_max_tokens_label()
            try:
                if self.ai_client is not None:
                    self.ai_client.ai_move_max_output_tokens = new_ai_tokens
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
            self.lbl_scores.show()
            self.lbl_last_breakdown.show()
            if self._last_move_word_details:
                self.word_tabs_container.show()
            else:
                self.word_tabs_container.hide()
            if self._last_move_reason.strip():
                self.lbl_last_reason.show()
            self.rack.show()
            if self._stored_split_sizes:
                self.split.setSizes(self._stored_split_sizes)
        else:
            self._stored_split_sizes = self.split.sizes()
            self.lbl_last_breakdown.hide()
            self.lbl_last_reason.hide()
            self.word_tabs_container.hide()
            self.btn_reroll.hide()
            self.rack.hide()
        self._game_ui_visible = visible

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
        # zruš pending placements a vráť písmená (neukladáme dočasné zmeny)
        if self.pending:
            self.board.clear_letters(self.pending)
            self.human_rack = restore_rack(self.human_rack, self.pending)
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
                last_move_reason=self._last_move_reason,
                last_move_reason_is_html=self._last_move_reason_is_html,
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
            saved_reason = str(st.get("last_move_reason", ""))
            saved_reason_is_html = bool(st.get("last_move_reason_is_html", False))
            self._clear_last_move_word_details()
            if saved_reason:
                self._set_last_move_reason(saved_reason, is_html=saved_reason_is_html)
            else:
                self._set_last_move_reason("")
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

    def create_iq_test(self) -> None:
        """Otvorí okno pre vytvorenie IQ testu."""
        from .iq_creator import IQTestCreatorWindow
        
        if not self.ai_rack:
            QMessageBox.warning(
                self,
                "IQ test",
                "AI nemá žiadne písmená na racku. Začni novú hru najprv.",
            )
            return
        
        dialog = IQTestCreatorWindow(
            board=self.board,
            ai_rack=self.ai_rack,
            variant_definition=self.variant_definition,
            ai_client=self.ai_client,
            parent=self,
        )
        dialog.exec()

    def edit_ai_prompt(self) -> None:
        """Open AI prompt editor dialog."""
        dialog = PromptEditorDialog(parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            # Reload prompt file in player.py will happen automatically
            # since it reads AI_PROMPT_FILE env var on each call
            QMessageBox.information(
                self,
                "Prompt aktualizovaný",
                f"Prompt bol úspešne aktualizovaný.\n"
                f"Používaný súbor: {dialog.get_current_prompt_file()}"
            )
    
    def open_agents_dialog(self) -> None:
        """Open agents activity dialog (non-modal)."""
        if self.agents_dialog is None:
            self.agents_dialog = AgentsDialog(parent=self)
        
        self.agents_dialog.show()
        self.agents_dialog.raise_()
        self.agents_dialog.activateWindow()
    
    def get_agents_dialog(self) -> AgentsDialog:
        """Get or create agents dialog instance."""
        if self.agents_dialog is None:
            self.agents_dialog = AgentsDialog(parent=self)
        return self.agents_dialog
    
    def open_opponent_settings(self) -> None:
        """Open opponent mode settings dialog."""
        from .settings_dialog import SettingsDialog as OpponentSettingsDialog
        
        dialog = OpponentSettingsDialog(
            parent=self,
            current_mode=self.opponent_mode,
            current_agent_name=self.selected_agent_name,
            available_agents=self.available_agents,
            game_in_progress=self.game_in_progress,
            ai_move_max_tokens=self.ai_move_max_tokens,
            ai_tokens_from_env=self._ai_tokens_from_env,
            user_defined_ai_tokens=self._user_defined_ai_tokens,
            repro_mode=self.repro_mode,
            repro_seed=self.repro_seed,
            active_tab_index=1,  # Open AI opponent tab
        )
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_mode = dialog.get_selected_mode()
            new_agent = dialog.get_selected_agent_name()
            
            # Store settings
            self.opponent_mode = new_mode
            self.selected_agent_name = new_agent
            
            # Check if OpenRouter models were configured
            openrouter_models = dialog.get_selected_openrouter_models()
            if openrouter_models:
                self.selected_ai_models = openrouter_models
                self.use_multi_model = True
                self.ai_move_max_tokens = dialog.get_openrouter_tokens()
                self._user_defined_ai_tokens = True
                self._update_max_tokens_label()
                try:
                    if self.ai_client is not None:
                        self.ai_client.ai_move_max_output_tokens = self.ai_move_max_tokens
                except Exception:
                    pass
                log.info("OpenRouter models updated: %d models", len(openrouter_models))
            
            # Update status message
            mode_name = new_mode.display_name_sk
            if new_mode == OpponentMode.AGENT and new_agent:
                self.status.showMessage(f"AI Režim: {mode_name} ({new_agent})")
            else:
                self.status.showMessage(f"AI Režim: {mode_name}")
            
            log.info("Opponent settings changed: mode=%s, agent=%s", new_mode.value, new_agent)
    
    def configure_openrouter_models(self) -> None:
        """Configure OpenRouter models for multi-model gameplay."""
        from .ai_config import AIConfigDialog
        
        # Use OpenRouter-specific token limit (default 8000)
        openrouter_tokens = int(os.getenv("OPENROUTER_MAX_TOKENS", "8000"))
        dialog = AIConfigDialog(
            parent=self,
            default_tokens=openrouter_tokens,
            lock_default=False,  # Token limit managed in settings
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.selected_ai_models = dialog.get_selected_models()
            self.use_multi_model = len(self.selected_ai_models) > 0
            shared_tokens = dialog.get_shared_tokens_value()
            self.ai_move_max_tokens = shared_tokens
            self._user_defined_ai_tokens = True
            self._update_max_tokens_label()
            try:
                if self.ai_client is not None:
                    self.ai_client.ai_move_max_output_tokens = shared_tokens
            except Exception:
                pass
            
            # Display selected models in the table immediately
            if self.use_multi_model:
                # Create result entries showing the selected models as "Ready"
                model_entries = []
                for model in self.selected_ai_models:
                    model_entries.append({
                        "model": model.get("id", ""),
                        "model_name": model.get("name", model.get("id", "Unknown")),
                        "move": None,
                        "score": 0,
                        "status": "ready",
                        "judge_valid": None,
                        "words": [],
                    })
                self.model_results_table.set_results(model_entries)
                
                # Update status bar
                model_count = len(self.selected_ai_models)
                self.status.showMessage(
                    f"✓ Aktivované {model_count} modelov (max tokeny: {shared_tokens})",
                    5000,
                )
            else:
                # Clear table when multi-model is disabled
                self.model_results_table.clear_results()
                self.status.showMessage(
                    "Multi-model režim deaktivovaný. Používa sa GPT-5-mini.", 5000
                )

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
