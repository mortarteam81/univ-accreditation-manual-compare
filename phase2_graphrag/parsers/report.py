"""보고서 주요내용 파서.

cycle_4 / cycle_3[i] 구조: { criterion, title, items: [{no, content, [mapping_note]}] }
"""
from __future__ import annotations

from typing import Any, Dict, Iterable

from .base import BaseParser, register_part


@register_part
class ReportParser(BaseParser):
    PART_KEY = "report"
    PART_LABEL = "편람 보고서 주요내용 비교"
    SOURCE_FILE = "편람 보고서 주요내용 비교_검수완료.json"

    def iter_items(self, cycle: str, criterion: dict, group: dict) -> Iterable[Dict[str, Any]]:
        for item in criterion.get("items") or []:
            if not isinstance(item, dict):
                continue
            no = item.get("no")
            content = item.get("content", "")
            out: Dict[str, Any] = {
                "item_key": f"item_{no}" if no is not None else f"item_{hash(content) & 0xFFFF:x}",
                "text": content,
                "raw": {
                    "no": no,
                    "content": content,
                },
            }
            if "mapping_note" in item:
                out["raw"]["mapping_note"] = item["mapping_note"]
                out["mapping_note"] = item["mapping_note"]
            yield out
