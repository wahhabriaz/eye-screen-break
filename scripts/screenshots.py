"""Render documentation screenshots of every page (dark + light) and the break overlay.

Uses a throw-away data directory seeded with SAMPLE history so charts are not empty.
This sample data exists only for screenshots and is never used by the application.
Nothing on the real desktop is captured.

Run: uv run python scripts/screenshots.py [output_dir] [--tall]
"""

from __future__ import annotations

import random
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from PySide6.QtCore import QPoint, QRect, Qt  # noqa: E402
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPixmap  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from eye_break.app import EyeBreakApp, parse_args  # noqa: E402
from eye_break.database.repositories import BreakRecord  # noqa: E402
from eye_break.ui.main_window import NAV  # noqa: E402
from eye_break.ui.overlay import BreakContent, BreakView  # noqa: E402
from eye_break.utils import paths  # noqa: E402


def seed(app: EyeBreakApp) -> None:
    rng = random.Random(7)
    today = datetime.now().replace(hour=9, minute=0, second=0, microsecond=0)
    for offset in range(29, -1, -1):
        day = today - timedelta(days=offset)
        if day.weekday() >= 5 and offset:
            continue
        hours = rng.uniform(4.5, 8)
        app.stats.add_active_seconds(day, hours * 3600 if offset else 3.2 * 3600)
        breaks = int(hours * 2) if offset else 6
        for i in range(breaks):
            start = day + timedelta(minutes=30 * (i + 1))
            roll = rng.random()
            outcome = "completed" if roll < 0.82 else ("skipped" if roll < 0.93 else "interrupted")
            actual = 30 if outcome == "completed" else rng.uniform(2, 20)
            app.stats.record_break(BreakRecord(start, start + timedelta(seconds=actual), 30, actual,
                                               outcome, "scheduled", "gentle"))
            if rng.random() < 0.1:
                app.stats.record_break(BreakRecord(start, start, 30, 0, "snoozed", "scheduled", "gentle"))


def overlay_shot(out: Path, size=(1600, 900)) -> None:
    w, h = size
    canvas = QPixmap(w, h)
    p = QPainter(canvas)
    grad = QLinearGradient(0, 0, w, h)
    grad.setColorAt(0, QColor("#4C7A8C"))
    grad.setColorAt(1, QColor("#C9A27A"))
    p.fillRect(0, 0, w, h, grad)
    for x, y, ww, hh in ((120, 90, 760, 540), (700, 260, 760, 560)):
        p.fillRect(x, y, ww, hh, QColor("#F4F5F7"))
        p.fillRect(x, y, ww, 34, QColor("#D9DDE2"))
    p.fillRect(0, 0, w, h, QColor(0, 0, 0, round(255 * 0.8)))
    view = BreakView(duration=30, quote="Your work can wait. Your health cannot.",
                     instruction="Look at something about 20 feet (6 metres) away and relax your eyes.",
                     snoozes_left=None)
    from eye_break.ui.overlay import OverlayOptions

    content = BreakContent(view, OverlayOptions())
    content.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    content.setStyleSheet("background: transparent;")
    content.set_remaining(18)
    content.progress._set(0.4)
    content.adjustSize()
    content.resize(820, content.sizeHint().height())
    content.render(p, QPoint((w - content.width()) // 2, (h - content.height()) // 2), QRect(),
                   BreakContent.RenderFlag.DrawChildren)
    p.end()
    canvas.save(str(out / "overlay.png"))


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    tall = "--tall" in sys.argv
    out = Path(args[0]) if args else ROOT / "docs" / "screenshots"
    out.mkdir(parents=True, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="eyebreak-shots-")
    paths.set_data_dir(tmp)
    qt = QApplication(sys.argv[:1])
    qt.setStyle("Fusion")
    app = EyeBreakApp(qt, parse_args(["--data-dir", tmp]))
    seed(app)
    app.manager.scheduler.work_elapsed = 17 * 60 + 24
    win = app.window
    win.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    win.resize(1180, 1700 if tall else 800)
    win.show()
    for theme in ("dark", "light"):
        app.theme.apply(theme, "teal")
        for key, *_ in NAV:
            win.show_page(key)
            for _ in range(3):
                qt.processEvents()
            win.grab().save(str(out / f"{key}-{theme}.png"))
    overlay_shot(out)
    app.manager.stop()
    app.conn.close()
    print("Screenshots written to", out)


if __name__ == "__main__":
    main()
