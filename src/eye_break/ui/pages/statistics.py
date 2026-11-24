from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QMessageBox

from eye_break.services.statistics_service import PERIODS
from eye_break.ui.components import (
    BarChart,
    Card,
    Page,
    Segmented,
    StatTile,
    button,
    format_duration,
    format_rate,
    label,
    legend,
    tile_grid,
)
from eye_break.ui.context import AppContext
from eye_break.ui.themes import current


class StatisticsPage(Page):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__("Statistics", "Your break history is stored only on this computer.")
        self.ctx = ctx
        self.period = "7d"

        bar = QHBoxLayout()
        self.seg = Segmented([(v, k) for k, v in PERIODS.items()], self.period)
        self.seg.changed.connect(self._on_period)
        bar.addWidget(self.seg)
        bar.addStretch(1)
        bar.addWidget(button("Export CSV", None, "download", self._export))
        bar.addWidget(button("Delete history", "danger", "trash", self._delete))
        self.column.addLayout(bar)

        self.t_completed = StatTile("Completed")
        self.t_skipped = StatTile("Skipped")
        self.t_snoozed = StatTile("Snoozed")
        self.t_interrupted = StatTile("Interrupted")
        self.t_rate = StatTile("Completion rate")
        self.t_break = StatTile("Total break time")
        self.t_active = StatTile("Active computer time", caption="Detected input, not screen time")
        self.t_streak = StatTile("Current streak")
        self.add(tile_grid([self.t_completed, self.t_skipped, self.t_snoozed, self.t_interrupted,
                            self.t_rate, self.t_break, self.t_active, self.t_streak], 4))

        self.charts_note = label("", "hint")
        self.add(self.charts_note)
        self.c_breaks = BarChart(["Completed", "Skipped", "Interrupted"])
        self.breaks_card, self.breaks_legend_holder = self._chart_card("Break completion", self.c_breaks)
        self.c_active = BarChart(["Active time"], formatter=lambda v: f"{v:.1f}h" if v else "0")
        self.active_card, _ = self._chart_card("Detected active computer time (hours)", self.c_active)
        self.c_duration = BarChart(["Break time"], formatter=lambda v: f"{v:.0f}m" if v >= 1 else f"{v:.1f}m")
        self.duration_card, _ = self._chart_card("Total break time (minutes)", self.c_duration)
        self.add(label("A day counts toward your streak when at least 80% of its breaks are completed. "
                       "Days without breaks neither extend nor break a streak.", "hint", wrap=True))
        self.finish()
        ctx.manager.stats_changed.connect(self.refresh)

    def _chart_card(self, title: str, chart: BarChart):
        card = Card()
        card.body.addWidget(label(title, "section"))
        card.body.addWidget(chart)
        self.add(card)
        return card, card.body

    def showEvent(self, e) -> None:  # noqa: N802
        super().showEvent(e)
        self.refresh()

    def _on_period(self, period: str) -> None:
        self.period = period
        self.refresh()

    def refresh(self) -> None:
        if not self.isVisible():
            return
        today = date.today()
        s = self.ctx.stats.summary(self.period, today)
        pending = max(0.0, self.ctx.manager.pending_active)
        self.t_completed.set(str(s.completed))
        self.t_skipped.set(str(s.skipped))
        self.t_snoozed.set(str(s.snoozed))
        self.t_interrupted.set(str(s.interrupted))
        self.t_rate.set(format_rate(s.rate))
        self.t_break.set(format_duration(s.break_seconds))
        self.t_active.set(format_duration(s.active_seconds + pending))
        self.t_streak.set(f"{s.current_streak} day{'' if s.current_streak == 1 else 's'}",
                          f"Longest: {s.longest_streak}")

        chart_summary = s
        if self.period == "today" or len(s.days) < 2:
            chart_summary = self.ctx.stats.summary("7d", today)
            self.charts_note.setText("Charts show the last 7 days.")
        else:
            self.charts_note.setText("")
        days = chart_summary.days[-60:]  # keep bars legible for long ranges
        if self.period == "all" and len(chart_summary.days) > 60:
            self.charts_note.setText("Charts show the most recent 60 days.")
        fmt = "%a" if len(days) <= 7 else "%d %b"
        labels = [d.day.strftime(fmt) for d in days]
        t = current()
        self.c_breaks.set_data(labels, [(d.completed, d.skipped, d.interrupted) for d in days],
                               [t.accent, t.text_subtle, t.warning])
        today_extra = pending if days and days[-1].day == today else 0
        self.c_active.set_data(labels, [((d.active_seconds + (today_extra if d.day == today else 0)) / 3600,)
                                        for d in days], [t.accent])
        self.c_duration.set_data(labels, [(d.break_seconds / 60,) for d in days], [t.accent])
        self.charts_note.setVisible(bool(self.charts_note.text()))
        if not hasattr(self, "_legend"):
            self._legend = legend([("Completed", t.accent), ("Skipped", t.text_subtle),
                                   ("Interrupted", t.warning)])
            self.breaks_card.body.addWidget(self._legend)

    def on_theme(self) -> None:
        if hasattr(self, "_legend"):
            self._legend.setParent(None)  # detach now; deleteLater alone leaves it visible until idle
            self._legend.deleteLater()
            del self._legend
        self.refresh()

    def _export(self) -> None:
        default = f"eye-break-history-{datetime.now():%Y%m%d}.csv"
        path, _ = QFileDialog.getSaveFileName(self, "Export break history", default, "CSV files (*.csv)")
        if not path:
            return
        try:
            count = self.ctx.stats.export_csv(Path(path))
        except OSError as exc:
            QMessageBox.warning(self, "Export failed", f"Could not write the file:\n{exc}")
            return
        QMessageBox.information(self, "Export complete", f"Exported {count} break records.")

    def _delete(self) -> None:
        answer = QMessageBox.question(
            self, "Delete history",
            "Permanently delete all break history and activity statistics? This cannot be undone.",
            QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Yes,
            QMessageBox.StandardButton.Cancel,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.ctx.manager.discard_pending_activity()
            self.ctx.stats.clear()
            self.ctx.manager.stats_changed.emit()
