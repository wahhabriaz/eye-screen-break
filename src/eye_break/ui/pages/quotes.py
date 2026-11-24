from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLineEdit, QListWidget

from eye_break.services.settings_service import MAX_CUSTOM_QUOTE_LENGTH, QUOTE_CATEGORIES
from eye_break.ui.components import Card, Page, SettingRow, ToggleSwitch, button, label, section
from eye_break.ui.context import AppContext

CATEGORY_LABELS = {
    "eyes": ("Eye health", "Gentle reminders about resting your eyes."),
    "breaks": ("Screen breaks", "Why short pauses matter."),
    "habits": ("Healthy habits", "Building a sustainable routine."),
    "rest": ("Rest and recovery", "Permission to slow down."),
    "balance": ("Work–life balance", "Perspective beyond the screen."),
    "productivity": ("Sustainable productivity", "Rest as part of doing good work."),
    "wellbeing": ("Physical well-being", "Posture, breathing, movement."),
}


class QuotesPage(Page):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__("Quotations", "Messages shown during breaks rotate automatically and avoid repeats.")
        self.ctx = ctx
        s = ctx.s

        show = Card()
        section(show, "Display")
        q = ToggleSwitch(s.show_quotes, "Show quotations")
        q.toggled.connect(lambda v: self._update(show_quotes=v))
        show.body.addWidget(SettingRow("Show quotations", "", q))
        ins = ToggleSwitch(s.show_instructions, "Show relaxation instructions")
        ins.toggled.connect(lambda v: self._update(show_instructions=v))
        show.body.addWidget(SettingRow("Show relaxation instructions",
                                       "Practical tips such as looking into the distance or blinking naturally.", ins))
        self.add(show)

        cats = Card()
        section(cats, "Categories")
        self.pool_caption = label("", "caption")
        cats.body.addWidget(self.pool_caption)
        for key in QUOTE_CATEGORIES:
            title, desc = CATEGORY_LABELS[key]
            tg = ToggleSwitch(key in s.quote_categories, title)
            tg.toggled.connect(lambda v, k=key: self._toggle_category(k, v))
            cats.body.addWidget(SettingRow(title, desc, tg))
        self.add(cats)

        custom = Card()
        section(custom, "Your own quotations", "Custom quotations are always included in the rotation.")
        row = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setMaxLength(MAX_CUSTOM_QUOTE_LENGTH)
        self.input.setPlaceholderText("Write a short, encouraging reminder…")
        self.input.returnPressed.connect(self._add)
        row.addWidget(self.input, 1)
        row.addWidget(button("Add", "primary", "plus", self._add))
        custom.body.addLayout(row)
        self.error = label("", "error")
        self.error.hide()
        custom.body.addWidget(self.error)
        self.list = QListWidget()
        self.list.setMinimumHeight(140)
        self.list.setAccessibleName("Custom quotations")
        custom.body.addWidget(self.list)
        self.remove_btn = button("Remove selected", "danger", "trash", self._remove)
        custom.body.addWidget(self.remove_btn)
        self.empty = label("You have not added any quotations yet.", "hint")
        custom.body.addWidget(self.empty)
        self.add(custom)
        self.finish()
        self._refresh()
        self.list.itemSelectionChanged.connect(self._sync_buttons)

    def _update(self, **changes) -> None:
        self.ctx.update(**changes)
        self._refresh()

    def _toggle_category(self, key: str, on: bool) -> None:
        chosen = set(self.ctx.s.quote_categories)
        chosen.add(key) if on else chosen.discard(key)
        self._update(quote_categories=[c for c in QUOTE_CATEGORIES if c in chosen])

    def _add(self) -> None:
        text = self.input.text().strip()
        if not text:
            self._show_error("Please write something first.")
            return
        if text in self.ctx.s.custom_quotes:
            self._show_error("That quotation is already in your list.")
            return
        self.error.hide()
        self._update(custom_quotes=[*self.ctx.s.custom_quotes, text])
        self.input.clear()

    def _remove(self) -> None:
        selected = {i.text() for i in self.list.selectedItems()}
        if selected:
            self._update(custom_quotes=[q for q in self.ctx.s.custom_quotes if q not in selected])

    def _show_error(self, msg: str) -> None:
        self.error.setText(msg)
        self.error.show()

    def _refresh(self) -> None:
        s = self.ctx.s
        self.list.clear()
        self.list.addItems(s.custom_quotes)
        self.list.setVisible(bool(s.custom_quotes))
        self.empty.setVisible(not s.custom_quotes)
        pool = len(self.ctx.quotes.pool(s.quote_categories, s.custom_quotes))
        note = "" if s.quote_categories or s.custom_quotes else " (none selected — all built-in quotations will be used)"
        self.pool_caption.setText(f"{pool} quotations in rotation{note}.")
        self._sync_buttons()

    def _sync_buttons(self) -> None:
        self.remove_btn.setVisible(bool(self.ctx.s.custom_quotes))
        self.remove_btn.setEnabled(bool(self.list.selectedItems()))
