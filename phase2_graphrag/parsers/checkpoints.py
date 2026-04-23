"""주요 점검사항 파서.

cycle_4 / cycle_3[i] 구조:
  { criterion, title, items: [{no, content, [sub_items: [str]], [mapping_note]}] }

- items 자체를 Item 노드로 생성
- sub_items 는 Item 노드의 attrs 로 보존 (별도 노드화하지 않음: 구조적 의미 미약)
"""
from __future__ import annotations

from typing import Any, Dict, Iterable

from .base import BaseParser, register_part


@register_part
class CheckpointsParser(BaseParser):
    PART_KEY = "checkpoints"
    PART_LABEL = "편람 주요 점검사항 비교"
    SOURCE_FILE = "편람 주요 점검사항 비교_검수완료.json"

    def iter_items(self, cycle: str, criterion: dict, group: dict) -> Iterable[Dict[str, Any]]:
        for item in criterion.get("items") or []:
            if not isinstance(item, dict):
                continue
            no = item.get("no")
            content = item.get("content", "")
            sub_items = item.get("sub_items") or []
            # sub_items 는 search 대상 텍스트에도 포함시킴 (파이프로 구분)
            search_text = content
            if sub_items:
                search_text = content + " | " + " / ".join(map(str, sub_items))
            out: Dict[str, Any] = {
                "item_key": f"item_{no}" if no is not None else f"item_{hash(content) & 0xFFFF:x}",
                "text": search_text,
                "raw": {
                    "no": no,
                    "content": content,
                    "sub_items": sub_items,
                },
            }
            if "mapping_note" in item:
                out["raw"]["mapping_note"] = item["mapping_note"]
                out["mapping_note"] = item["mapping_note"]
            yield out
