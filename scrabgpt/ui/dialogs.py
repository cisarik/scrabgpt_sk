"""Pomocné UI dialógy.

Obsahuje `DownloadProgressDialog` pre sťahovanie wordlistu s priebežným
ukazovateľom (QProgressBar) a percentami. Sťahovanie prebieha v QThread,
aby UI nezamrzlo.
"""

from __future__ import annotations

from contextlib import suppress
import logging
import os
from pathlib import Path
import urllib.request

from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtWidgets import QDialog, QLabel, QProgressBar, QVBoxLayout, QWidget


log = logging.getLogger("scrabgpt")


# Kandidátne URL pre ENABLE wordlist (poradie pokusov)
ENABLE_URLS: list[str] = [
    "https://raw.githubusercontent.com/wordnik/wordlist/master/enable1.txt",
    "https://raw.githubusercontent.com/dwyl/english-words/master/word-lists/enable1.txt",
    "https://raw.githubusercontent.com/dolph/dictionary/master/enable1.txt",
    "https://raw.githubusercontent.com/nikiiv/wordlist/master/enable1.txt",
]


class _DownloadWorker(QObject):
    progress: Signal = Signal(int)
    finished: Signal = Signal(int)
    failed: Signal = Signal(str)

    def __init__(self, urls: list[str], dest: str) -> None:
        super().__init__()
        self.urls = urls
        self.dest = dest

    def run(self) -> None:
        try:
            # Guard: umožni vypnúť download v testoch/CI cez env
            enabled = os.getenv("SCRABGPT_ENABLE_DOWNLOADS", "1").lower()
            if enabled not in ("1", "true", "yes"):  # pragma: no cover - guard path
                self.failed.emit("downloads disabled")
                return
            # zaisti priecinky
            Path(self.dest).parent.mkdir(parents=True, exist_ok=True)
            last_err: str | None = None
            for _idx, url in enumerate(self.urls):
                try:
                    log.info(
                        "offline_download start url=%s dest=%s size=%s",
                        url,
                        self.dest,
                        "unknown",
                    )
                    with urllib.request.urlopen(url) as resp:
                        size_hdr = resp.headers.get("Content-Length")
                        total_size = int(size_hdr) if size_hdr and size_hdr.isdigit() else None
                        if total_size is not None:
                            log.info(
                                "offline_download start url=%s dest=%s size=%s",
                                url,
                                self.dest,
                                str(total_size),
                            )
                        read_bytes = 0
                        chunk = 64 * 1024
                        tmp_path = Path(f"{self.dest}.part")
                        with tmp_path.open("wb") as f:
                            while True:
                                data = resp.read(chunk)
                                if not data:
                                    break
                                f.write(data)
                                read_bytes += len(data)
                                if total_size and total_size > 0:
                                    percent = int((read_bytes / total_size) * 100)
                                    self.progress.emit(min(percent, 100))
                                else:
                                    self.progress.emit(
                                        min(99, self.progress_value_guess(read_bytes))
                                    )
                    # validuj obsah: musí vyzerať ako ENABLE wordlist
                    if not self._validate_wordlist_file(str(tmp_path)):
                        with suppress(Exception):
                            tmp_path.unlink()
                        raise RuntimeError("downloaded file is not a valid ENABLE wordlist")
                    tmp_path.replace(self.dest)
                    self.progress.emit(100)
                    log.info("offline_download done bytes=%s", read_bytes)
                    self.finished.emit(read_bytes)
                    return
                except Exception as e:  # noqa: BLE001
                    last_err = str(e)
                    with suppress(Exception):
                        log.exception(
                            "offline_download fail url=%s dest=%s err=%s",
                            url,
                            self.dest,
                            e,
                        )
                    # skúsi ďalší mirror
                    continue
            # ak sme sa sem dostali, všetky pokusy zlyhali
            self.failed.emit(last_err or "download failed")
        except Exception as e:  # noqa: BLE001
            with suppress(Exception):
                log.exception("offline_download fail dest=%s err=%s", self.dest, e)
            self.failed.emit(str(e))

    def progress_value_guess(self, read_bytes: int) -> int:
        # jednoduchý monotónny rast (logaritmický tvar), aby bar neostal na 0
        # pri chýbajúcom Content-Length
        try:
            import math
            return int(min(99, 10 + 15 * math.log10(max(1, read_bytes))))
        except Exception:
            return 50

    def _validate_wordlist_file(self, path: str) -> bool:
        """Heuristika validácie: súbor by mal obsahovať množstvo riadkov
        s čistými slovami A–Z. Overíme aspoň počet a prítomnosť pár známych slov.

        Cieľ: odfiltrovať HTML/JSON chybové stránky ako neplatný wordlist.
        """
        try:
            total = 0
            good = 0
            has_cat = False
            has_tweens = False
            with Path(path).open(encoding="utf-8", errors="ignore") as f:
                for _i, line in enumerate(f):
                    total += 1
                    w = line.strip().upper()
                    if not w:
                        continue
                    # povoľ iba A–Z, žiadne medzery ani značky
                    if all("A" <= ch <= "Z" for ch in w):
                        good += 1
                        if w == "CAT":
                            has_cat = True
                        if w == "TWEENS":
                            has_tweens = True
            # musíme mať aspoň 10k dobrých riadkov a aspoň jedno zo známych slov
            return (good >= 10000) and (has_cat or has_tweens)
        except Exception:
            return False


class DownloadProgressDialog(QDialog):
    """Modálny dialóg s priebehom sťahovania.

    Ak sťahovanie skončí úspešne, dialóg sa automaticky zavrie. Pri zlyhaní
    sa uloží chybová správa a dialóg sa zavrie; volajúci môže zobraziť notifikáciu.
    """

    def __init__(
        self,
        url_or_urls: str | list[str],
        dest: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Sťahujem wordlist…")
        lay = QVBoxLayout(self)
        self.lbl = QLabel("Inicializujem…")
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        lay.addWidget(self.lbl)
        lay.addWidget(self.bar)
        self._ok: bool = False
        self._error: str = ""

        self._thread = QThread(self)
        urls: list[str] = (
            list(url_or_urls) if isinstance(url_or_urls, list) else [str(url_or_urls)]
        )
        # doplň implicitné mirrory na koniec
        for mirror in ENABLE_URLS:
            if mirror not in urls:
                urls.append(mirror)
        self._worker = _DownloadWorker(urls, dest)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_done)
        self._worker.failed.connect(self._on_fail)
        self._worker.finished.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)

    def start(self) -> None:
        self._thread.start()

    @property
    def ok(self) -> bool:
        return self._ok

    @property
    def error(self) -> str:
        return self._error

    def _on_progress(self, percent: int) -> None:
        self.bar.setValue(percent)
        self.lbl.setText(f"{percent}%")

    def _on_done(self, _bytes: int) -> None:
        self._ok = True
        self.accept()

    def _on_fail(self, msg: str) -> None:
        self._ok = False
        self._error = msg
        self.reject()


