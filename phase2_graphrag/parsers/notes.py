"""유의사항 및 관련정책 파서.

cycle_4 / cycle_3[i] 구조: { criterion, title, items: [{no, content, [mapping_note]}] }
보고서 주요내용과 구조가 동일하므로 Report 파서를 재사용해도 되지만,
Part 식별을 위해 별도 클래스로 분리.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable

from .base import BaseParser, register_part


@register_part
class NotesParser(BaseParser):
    PART_KEY = "notes"
    PART_LABEL = "편람 유의사항 및 관련정책 비교"
    SOURCE_FILE = "편람 유의사항 및 관련정책 비교_검수완료.json"

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
