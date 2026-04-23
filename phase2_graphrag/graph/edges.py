"""엣지 생성 유틸리티.

엣지 dict 스키마:
  {
    "source": node_id,
    "target": node_id,
    "type": "CONTAINS" | "MAPS_TO" | "MERGED_WITH" | "SPLIT_INTO" |
            "MOVED_TO" | "ITEM_MAPS_TO" | "SIMILAR_TO",
    "attrs": { ... }
  }

mapping_type 파싱 로직:
  mapping_type 문자열에서 키워드를 추출해 엣지 타입들을 도출한다.
  예:
    '통합 (N:1)'         -> ['통합']            -> MAPS_TO(type=통합) + MERGED_WITH
    '통합·이동 (N:1)'    -> ['통합', '이동']   -> MAPS_TO(type=통합·이동) + MERGED_WITH + (MOVED_TO는 타 파트/준거를 타겟팅해야 해서 여기선 미생성)
    '분할 (1:N)'         -> ['분할']            -> MAPS_TO(type=분할) + SPLIT_INTO
"""
from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .nodes import criterion_id, item_id


# ------------------------------------------------------------------
# mapping_type 파싱
# ------------------------------------------------------------------

_KW_MERGE = ("통합",)
_KW_SPLIT = ("분할", "분리")
_KW_MOVE = ("이동",)


def parse_mapping_type(mapping_type: Optional[str]) -> Dict[str, Any]:
    """mapping_type 문자열을 구조화된 정보로 분해.

    반환 dict:
      {
        "raw":  원본 문자열,
        "base": '유지' / '수정' / '이동' / '통합' / '분할' / '신설' / '삭제' / '' ...,
        "cardinality": '1:1' / 'N:1' / '1:N' / '',
        "is_merge": bool,  # 통합 포함
        "is_split": bool,  # 분할/분리 포함
        "is_move":  bool,  # 이동 포함
      }
    """
    mt = (mapping_type or "").strip()
    result = {
        "raw": mt,
        "base": "",
        "cardinality": "",
        "is_merge": any(k in mt for k in _KW_MERGE),
        "is_split": any(k in mt for k in _KW_SPLIT),
        "is_move": any(k in mt for k in _KW_MOVE),
    }
    m = re.search(r"\((\d:\d|N:\d|\d:N)\)", mt)
    if m:
        result["cardinality"] = m.group(1)
    # base: 괄호 앞 덩어리를 가져온다 (복합형은 '·' 구분)
    base = re.split(r"\s*\(", mt, maxsplit=1)[0].strip()
    result["base"] = base
    return result


# ------------------------------------------------------------------
# group 단위 엣지 빌드
# ------------------------------------------------------------------

def build_group_edges(
    part_key: str,
    group: dict,
) -> List[Dict[str, Any]]:
    """한 group(동일 theme 로 묶인 3주기↔4주기 매핑)에 대해 엣지를 생성.

    - MAPS_TO: 모든 3주기 Criterion → 4주기 Criterion (dict 인 경우에만)
               ※ 4주기가 없으면(=삭제) MAPS_TO 생성하지 않음 → 고립 노드로 남음 (meta 에 기록)
    - MERGED_WITH: 3주기 내부에서 여러 준거가 통합된 경우, 3주기 Criterion 쌍끼리 양방향 엣지
    - SPLIT_INTO: 분할/분리 시 4주기 여러 준거로 흩어지는 케이스 — 현 데이터상 group 당 1개의 4주기만 있어
                  파일 내부 단일 group 만으로는 완전히 표현 불가. 메타 정보로만 보존 (note 에 'split' 기록).
    """
    mp = parse_mapping_type(group.get("mapping_type"))
    gid = group.get("group_id")
    theme = group.get("theme")
    mnote = group.get("mapping_note")

    edges: List[Dict[str, Any]] = []

    c4 = group.get("cycle_4")
    c4_crit = str(c4.get("criterion")) if isinstance(c4, dict) else None
    c3_list = group.get("cycle_3") or []

    c4_node = criterion_id("4", part_key, c4_crit) if c4_crit else None

    # 1) MAPS_TO: 3주기 각 준거 → 4주기 준거
    if c4_node:
        for c3 in c3_list:
            if not isinstance(c3, dict):
                continue
            c3_crit = str(c3.get("criterion"))
            c3_node = criterion_id("3", part_key, c3_crit)
            edges.append({
                "source": c3_node,
                "target": c4_node,
                "type": "MAPS_TO",
                "attrs": {
                    "mapping_type": mp["raw"],
                    "mapping_base": mp["base"],
                    "cardinality": mp["cardinality"],
                    "group_id": gid,
                    "theme": theme,
                    "mapping_note": mnote,
                },
            })

    # 2) MERGED_WITH: 3주기 쌍끼리 (통합인 경우만)
    if mp["is_merge"] and len(c3_list) >= 2:
        crit_nums = [str(c.get("criterion")) for c in c3_list if isinstance(c, dict)]
        for i in range(len(crit_nums)):
            for j in range(i + 1, len(crit_nums)):
                a = criterion_id("3", part_key, crit_nums[i])
                b = criterion_id("3", part_key, crit_nums[j])
                edges.append({
                    "source": a,
                    "target": b,
                    "type": "MERGED_WITH",
                    "attrs": {
                        "group_id": gid,
                        "theme": theme,
                        "merged_into": c4_node,
                    },
                })

    # 3) SPLIT_INTO, MOVED_TO: 파일 내부 단일 group 만으로는 완전히 표현 불가.
    #    → MAPS_TO 엣지의 attrs 에 플래그로 보존. 필요 시 Phase 2 확장 단계에서 외부 추론으로 추가.

    return edges


# ------------------------------------------------------------------
# item 수준 mapping_note 파싱
# ------------------------------------------------------------------

# '4주기 1.5 item3' 또는 '4주기 1.5 (item3)' 또는 '4주기 1.5로' 같은 패턴.
_RE_ITEM_REF = re.compile(
    r"(?P<cycle>3|4)\s*주기\s*(?P<crit>\d+(?:\.\d+)?)"
    r"(?:\s*(?:item\s*|아이템\s*|no\.?\s*)(?P<no>\d+))?"
)


def parse_item_mapping_note(
    note: str,
    src_cycle: str,
) -> List[Dict[str, Any]]:
    """item 의 mapping_note 텍스트에서 대상 (cycle, criterion, [item_no]) 를 추출.

    보수적으로 접근: 명확히 매칭되는 참조만 반환.
    '3주기' 문자열이 note 에 등장하고 src_cycle 도 '3'인 경우는
    자기 자신을 참조하는 것이므로 타겟으로 사용하지 않는다.
    """
    refs: List[Dict[str, Any]] = []
    for m in _RE_ITEM_REF.finditer(note or ""):
        ref_cycle = m.group("cycle")
        if ref_cycle == src_cycle:
            # self-reference → skip (mapping_note 는 보통 타 cycle 로의 이동을 기술)
            continue
        refs.append({
            "cycle": ref_cycle,
            "criterion": m.group("crit"),
            "item_no": m.group("no"),
        })
    return refs


def build_item_mapping_edges(
    src_node_id: str,
    src_part_key: str,
    src_cycle: str,
    mapping_note: str,
    node_index: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """mapping_note 에서 타겟 Item/Criterion 노드를 자동 추론해 ITEM_MAPS_TO 엣지를 만든다.

    * node_index: {node_id: node_dict} — 대상 노드 존재 확인용
    * 타겟 item 노드 ID 후보를 여러 개 시도 (item_no 기반) → 있으면 Item 타겟, 없으면 Criterion 타겟
    * 실패 시 엣지 없이 note 만 보존 (호출부에서 노드 attrs 로 유지)
    """
    edges: List[Dict[str, Any]] = []
    refs = parse_item_mapping_note(mapping_note, src_cycle)
    if not refs:
        return edges
    # 파트 간 이동도 허용: mapping_note 에 '이동' 이 있으면 타 파트로 가는 경우가 많지만
    # 파트 자체는 note 에서 유추하기 어려워 동일 파트로만 시도. 실패 시 Criterion 노드로 폴백.
    for ref in refs:
        target_cycle = ref["cycle"]
        target_crit = ref["criterion"]
        target_item_no = ref["item_no"]
        target_node = None
        if target_item_no is not None:
            candidate = f"item_{target_cycle}_{src_part_key}_{target_crit}_item_{target_item_no}"
            if candidate in node_index:
                target_node = candidate
        if not target_node:
            # Criterion 폴백
            candidate = f"crit_{target_cycle}_{src_part_key}_{target_crit}"
            if candidate in node_index:
                target_node = candidate
        if target_node:
            edges.append({
                "source": src_node_id,
                "target": target_node,
                "type": "ITEM_MAPS_TO",
                "attrs": {
                    "note": mapping_note,
                    "inferred": True,
                    "target_item_no": target_item_no,
                },
            })
    return edges
