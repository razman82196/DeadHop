from __future__ import annotations
from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QTextEdit, QPushButton
from PyQt6.QtCore import QSize
try:
    from rapidfuzz import process as rf_process
except Exception:  # optional dependency
    rf_process = None


class Composer(QWidget):
    messageSubmitted = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.input = QTextEdit(self)
        self.input.setPlaceholderText("Type a message… (Enter to send)")
        self.input.setAcceptRichText(False)
        # Ensure Tab is used for completion instead of moving focus
        self.input.setTabChangesFocus(False)
        # Single-line behavior: no wrapping, no scrollbars, fixed height to one line
        try:
            self.input.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        except Exception:
            pass
        try:
            self.input.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self.input.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        except Exception:
            pass
        try:
            fm = self.input.fontMetrics()
            # Make the input approximately twice the previous height
            base = fm.lineSpacing()
            line_h = int(base * 2.7) + 12  # ~2x previous size + a bit more padding
            self.input.setFixedHeight(line_h)
            self.setMinimumHeight(line_h)
        except Exception:
            # Fallback for platforms without metrics
            self.input.setFixedHeight(68)
        layout.addWidget(self.input, 1)

        self.btn = QPushButton("Send", self)
        self.btn.clicked.connect(self._submit)
        layout.addWidget(self.btn, 0)

        self.input.installEventFilter(self)

        # Completion state
        self._completion_names: list[str] = []
        self._cycle_matches: list[str] = []
        self._cycle_index: int = -1
        self._cycle_anchor: tuple[int, int] | None = None  # (start, end) of word

    def eventFilter(self, obj, ev):  # type: ignore[override]
        if obj is self.input and ev.type() == ev.Type.KeyPress:
            if ev.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                # Always submit on Enter; prevent newline insertion
                self._submit()
                return True
            if ev.key() == Qt.Key.Key_Tab:
                self._handle_tab(forward=not (ev.modifiers() & Qt.KeyboardModifier.ShiftModifier))
                return True
        return super().eventFilter(obj, ev)

    def _submit(self) -> None:
        # Replace any newlines with spaces to enforce single-line behavior
        text = self.input.toPlainText().replace("\n", " ").replace("\r", " ").strip()
        if text:
            self.messageSubmitted.emit(text)
            self.input.clear()
        # reset completion state
        self._cycle_matches = []
        self._cycle_index = -1
        self._cycle_anchor = None

    # ----- Completion API -----
    def set_completion_names(self, names: list[str]) -> None:
        # keep unique list, stable sort
        self._completion_names = sorted(set(names), key=str.lower)
        # reset cycle if names changed
        self._cycle_matches = []
        self._cycle_index = -1
        self._cycle_anchor = None

    def _current_word(self) -> tuple[int, int, str]:
        cur = self.input.textCursor()
        pos = cur.position()
        text = self.input.toPlainText()
        if not text:
            return 0, 0, ""
        # find word boundaries: letters, digits, _ - #
        start = pos
        while start > 0 and text[start - 1] not in " \t\n\r":
            start -= 1
        end = pos
        while end < len(text) and text[end] not in " \t\n\r":
            end += 1
        return start, end, text[start:end]

    def _handle_tab(self, forward: bool = True) -> None:
        start, end, word = self._current_word()
        if self._cycle_anchor is None or self._cycle_anchor != (start, end):
            # New cycle
            self._cycle_anchor = (start, end)
            # Candidates: names starting with word (case-insens.)
            low = word.lower()
            cands = [n for n in self._completion_names if n.lower().startswith(low)] if low else list(self._completion_names)
            # If none, try fuzzy with rapidfuzz (top 10 by score)
            if not cands and rf_process and low:
                try:
                    scored = rf_process.extract(low, self._completion_names, limit=10)
                    # scored: list of tuples (match, score, idx)
                    cands = [m for (m, _score, _idx) in sorted(scored, key=lambda t: t[1], reverse=True)]
                except Exception:
                    pass
            # If at line start, prefer appending ':' after nick
            self._cycle_matches = cands
            self._cycle_index = 0 if cands else -1
        else:
            # Continue cycle
            if not self._cycle_matches:
                return
            if forward:
                self._cycle_index = (self._cycle_index + 1) % len(self._cycle_matches)
            else:
                self._cycle_index = (self._cycle_index - 1) % len(self._cycle_matches)

        if self._cycle_index < 0 or not self._cycle_matches:
            return
        nick = self._cycle_matches[self._cycle_index]
        # Replace the word in the editor
        cur = self.input.textCursor()
        doc_text = self.input.toPlainText()
        prefix = doc_text[:start]
        suffix = doc_text[end:]
        at_line_start = (not prefix) or prefix.endswith("\n")
        insert = nick + (": " if at_line_start else "")
        new_text = prefix + insert + suffix
        # Set text and move cursor
        self.input.setPlainText(new_text)
        new_pos = len(prefix) + len(nick) + (2 if at_line_start else 0)
        cur.setPosition(new_pos)
        self.input.setTextCursor(cur)
        # keep anchor updated to allow cycling
        self._cycle_anchor = (start, start + len(nick))
