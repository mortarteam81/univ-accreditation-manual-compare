"""개요 파서.

cycle_4 / cycle_3[i] 구조: { criterion, title, content }
→ Item 1개 (content 문자열)
"""
from __future__ import annotations

from typing import Any, Dict, Iterable

from .base import BaseParser, register_part


@register_part
class OverviewParser(BaseParser):
    PART_KEY = "overview"
    PART_LABEL = "편람 개요 비교"
    SOURCE_FILE = "편람 개요 비교_검수완료.json"

    def iter_items(self, cycle: str, criterion: dict, group: dict) -> Iterable[Dict[str, Any]]:
        content = criterion.get("content")
        if not content:
            return
        yield {
            "item_key": "content",
            "text": content,
            "raw": {"content": content},
        }
