"""Quotation and instruction rotation without frequent repetition."""

from __future__ import annotations

import json
import random
from collections.abc import Callable
from pathlib import Path

RECENT_FRACTION = 0.6  # never repeat a quote until ~60% of the pool has been shown


class QuoteService:
    def __init__(
        self,
        assets_file: Path,
        load_recent: Callable[[], list[str]] | None = None,
        save_recent: Callable[[list[str]], None] | None = None,
        rng: random.Random | None = None,
    ) -> None:
        data = json.loads(assets_file.read_text(encoding="utf-8"))
        self.builtin: list[dict[str, str]] = data["quotes"]
        self.instructions: list[str] = data["instructions"]
        self._rng = rng or random.Random()
        self._save_recent = save_recent
        self._recent: list[str] = load_recent() if load_recent else []
        self._recent_instr: list[str] = []

    def pool(self, categories: list[str], custom: list[str]) -> list[str]:
        quotes = [q["text"] for q in self.builtin if q["category"] in categories]
        return list(dict.fromkeys(quotes + custom))

    def next_quote(self, categories: list[str], custom: list[str]) -> str:
        pool = self.pool(categories, custom)
        if not pool:
            pool = [q["text"] for q in self.builtin]
        choice = self._pick(pool, self._recent)
        if self._save_recent:
            self._save_recent(self._recent)
        return choice

    def next_instruction(self) -> str:
        return self._pick(self.instructions, self._recent_instr)

    def _pick(self, pool: list[str], recent: list[str]) -> str:
        window = int(len(pool) * RECENT_FRACTION)
        blocked = set(recent[-window:]) if window else set()
        candidates = [q for q in pool if q not in blocked] or pool
        choice = self._rng.choice(candidates)
        recent.append(choice)
        del recent[:-200]  # bounded history
        return choice
