"""근거자료 파서.

cycle_4 / cycle_3[i] 구조:
  {
    criterion, title,
    정보공시: [str | {content, mapping_note}],
    제출자료_관련규정: [...],
    제출자료_첨부: [...],
    현지확인자료: [...],
    현지면담: [...],
    시설방문: [...],
  }

각 서브필드의 각 항목을 하나의 Item 노드로 만든다.
문자열/dict 혼합 리스트를 모두 처리한다.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable

from .base import BaseParser, register_part


#: 근거자료의 6개 서브필드 순서 (안정적인 노드 id 를 위해 고정).
EVIDENCE_SUBFIELDS = (
    "정보공시",
    "제출자료_관련규정",
    "제출자료_첨부",
    "현지확인자료",
    "현지면담",
    "시설방문",
)


@register_part
class EvidenceParser(BaseParser):
    PART_KEY = "evidence"
    PART_LABEL = "편람 근거자료 비교"
    SOURCE_FILE = "편람 근거자료 비교_검수완료.json"

    def iter_items(self, cycle: str, criterion: dict, group: dict) -> Iterable[Dict[str, Any]]:
        for subfield in EVIDENCE_SUBFIELDS:
            lst = criterion.get(subfield) or []
            for idx, elem in enumerate(lst):
                if isinstance(elem, str):
                    content = elem
                    mapping_note = None
                elif isinstance(elem, dict):
                    content = elem.get("content", "")
                    mapping_note = elem.get("mapping_note")
                else:
                    continue
                out: Dict[str, Any] = {
                    "item_key": f"{subfield}_{idx}",
                    "text": content,
                    "subfield": subfield,
                    "raw": {
                        "subfield": subfield,
                        "idx": idx,
                        "content": content,
                    },
                }
                if mapping_note:
                    out["raw"]["mapping_note"] = mapping_note
                    out["mapping_note"] = mapping_note
                yield out
