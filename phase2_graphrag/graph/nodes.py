"""노드 생성 유틸리티.

ID 체계 (승인됨):
  Cycle:     cycle_{3|4}
  Part:      part_{part_key}
  Criterion: crit_{cycle}_{part_key}_{criterion_number}
  Item:      item_{cycle}_{part_key}_{criterion_number}_{item_key}

모든 id는 사용자 설계 승인을 받은 형태를 따른다.
노드 dict 스키마:
  {
    "id": str,
    "type": "Cycle" | "Part" | "Criterion" | "Item",
    "attrs": { ... }
  }
"""
from __future__ import annotations

from typing import Any, Dict


# ------------------------------------------------------------------
# Cycle / Part
# ------------------------------------------------------------------

def make_cycle_node(cycle: str) -> Dict[str, Any]:
    return {
        "id": f"cycle_{cycle}",
        "type": "Cycle",
        "attrs": {"cycle": cycle, "label": f"{cycle}주기"},
    }


def make_part_node(part_key: str, part_label: str, source_file: str) -> Dict[str, Any]:
    return {
        "id": f"part_{part_key}",
        "type": "Part",
        "attrs": {
            "part_key": part_key,
            "label": part_label,
            "source_file": source_file,
        },
    }


# ------------------------------------------------------------------
# Criterion
# ------------------------------------------------------------------

def criterion_id(cycle: str, part_key: str, criterion: str) -> str:
    return f"crit_{cycle}_{part_key}_{criterion}"


def make_criterion_node(
    cycle: str,
    part_key: str,
    criterion_dict: dict,
    group: dict,
) -> Dict[str, Any]:
    cnum = str(criterion_dict.get("criterion", ""))
    return {
        "id": criterion_id(cycle, part_key, cnum),
        "type": "Criterion",
        "attrs": {
            "cycle": cycle,
            "part_key": part_key,
            "criterion": cnum,
            "title": criterion_dict.get("title", ""),
            "group_id": group.get("group_id"),
            "theme": group.get("theme"),
            "group_mapping_type": group.get("mapping_type"),
        },
    }


# ------------------------------------------------------------------
# Item
# ------------------------------------------------------------------

def item_id(cycle: str, part_key: str, criterion: str, item_key: str) -> str:
    return f"item_{cycle}_{part_key}_{criterion}_{item_key}"


def make_item_node(
    cycle: str,
    part_key: str,
    criterion_number: str,
    parsed_item: Dict[str, Any],
    group: dict,
) -> Dict[str, Any]:
    item_key = parsed_item["item_key"]
    return {
        "id": item_id(cycle, part_key, criterion_number, item_key),
        "type": "Item",
        "attrs": {
            "cycle": cycle,
            "part_key": part_key,
            "criterion": criterion_number,
            "item_key": item_key,
            "text": parsed_item.get("text", ""),
            "subfield": parsed_item.get("subfield"),
            "mapping_note": parsed_item.get("mapping_note"),
            "group_id": group.get("group_id"),
            "raw": parsed_item.get("raw", {}),
        },
    }
