import json
import random

from eye_break.services.quote_service import QuoteService
from eye_break.services.settings_service import QUOTE_CATEGORIES
from eye_break.utils.paths import assets_dir

QUOTES = assets_dir() / "quotes.json"


def test_library_size_and_categories():
    data = json.loads(QUOTES.read_text(encoding="utf-8"))
    assert len(data["quotes"]) >= 100
    assert {q["category"] for q in data["quotes"]} == set(QUOTE_CATEGORIES)
    assert len(data["instructions"]) >= 8


def test_no_repeats_within_window():
    svc = QuoteService(QUOTES, rng=random.Random(1))
    cats = list(QUOTE_CATEGORIES)
    pool_size = len(svc.pool(cats, []))
    window = int(pool_size * 0.6)
    shown = [svc.next_quote(cats, []) for _ in range(window)]
    assert len(set(shown)) == window


def test_category_filter_and_custom_quotes():
    svc = QuoteService(QUOTES, rng=random.Random(2))
    custom = ["My own reminder."]
    pool = svc.pool(["eyes"], custom)
    assert "My own reminder." in pool
    assert "Rest is part of doing good work." not in pool
    for _ in range(50):
        assert svc.next_quote(["eyes"], custom) in pool


def test_custom_only():
    svc = QuoteService(QUOTES)
    assert svc.next_quote([], ["Only me."]) == "Only me."


def test_empty_selection_falls_back_to_builtin():
    svc = QuoteService(QUOTES)
    assert svc.next_quote([], [])


def test_recent_history_persisted():
    saved: list[list[str]] = []
    svc = QuoteService(QUOTES, load_recent=lambda: ["x"], save_recent=lambda r: saved.append(list(r)))
    svc.next_quote(["eyes"], [])
    assert saved[-1][0] == "x" and len(saved[-1]) == 2
