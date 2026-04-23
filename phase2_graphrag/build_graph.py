"""Phase 2 메인 빌더.

입력: 최종작업(20260417) 폴더의 5개 _검수완료.json
출력: graph_nodes.json, graph_edges.json, embeddings.json, graph_meta.json

사용법:
    python build_graph.py --input-dir "/path/to/최종작업(20260417)" \
                          --output-dir "/path/to/output"
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime
from typing import Any, Dict, List

# 패키지 import 가 항상 동작하도록 sys.path 조정.
HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from parsers import (  # noqa: E402
    PART_REGISTRY,
    OverviewParser,
    ReportParser,
    EvidenceParser,
    CheckpointsParser,
    NotesParser,
)
from graph.nodes import (  # noqa: E402
    make_cycle_node,
    make_part_node,
    make_criterion_node,
    make_item_node,
    criterion_id,
    item_id,
)
from graph.edges import (  # noqa: E402
    build_group_edges,
    build_item_mapping_edges,
    parse_mapping_type,
)


# 등록 순서 고정 (출력 안정성).
PARSER_ORDER = [
    OverviewParser,
    ReportParser,
    EvidenceParser,
    CheckpointsParser,
    NotesParser,
]


def load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: str, data: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def build(input_dir: str, output_dir: str) -> Dict[str, Any]:
    # ------------------------------------------------------------------
    # 0) 파일 로드 및 파서 인스턴스화
    # ------------------------------------------------------------------
    parsers: List[Any] = []
    missing_files: List[str] = []
    for cls in PARSER_ORDER:
        path = os.path.join(input_dir, cls.SOURCE_FILE)
        if not os.path.exists(path):
            missing_files.append(cls.SOURCE_FILE)
            continue
        data = load_json(path)
        parsers.append(cls(data))
    if missing_files:
        raise FileNotFoundError(f"입력 디렉토리에 다음 파일이 없음: {missing_files}")

    # ------------------------------------------------------------------
    # 1) 노드 생성
    # ------------------------------------------------------------------
    nodes: List[Dict[str, Any]] = []
    nodes_seen: set = set()

    def add_node(node: Dict[str, Any]) -> None:
        if node["id"] in nodes_seen:
            return
        nodes_seen.add(node["id"])
        nodes.append(node)

    # Cycle 노드
    for c in ("3", "4"):
        add_node(make_cycle_node(c))

    # Part 노드
    for parser in parsers:
        add_node(make_part_node(parser.PART_KEY, parser.PART_LABEL, parser.SOURCE_FILE))

    # Criterion / Item 노드
    for parser in parsers:
        for cycle, crit_dict, group in parser.iter_criteria():
            crit_node = make_criterion_node(cycle, parser.PART_KEY, crit_dict, group)
            add_node(crit_node)
            crit_num = str(crit_dict.get("criterion", ""))
            for parsed_item in parser.iter_items(cycle, crit_dict, group):
                item_node = make_item_node(
                    cycle, parser.PART_KEY, crit_num, parsed_item, group
                )
                add_node(item_node)

    node_index: Dict[str, Dict[str, Any]] = {n["id"]: n for n in nodes}

    # ------------------------------------------------------------------
    # 2) 엣지 생성
    # ------------------------------------------------------------------
    edges: List[Dict[str, Any]] = []

    # 2-1) CONTAINS: Cycle → Part (파트는 양쪽 cycle 에 공통으로 달린다)
    for parser in parsers:
        for c in ("3", "4"):
            edges.append({
                "source": f"cycle_{c}",
                "target": f"part_{parser.PART_KEY}",
                "type": "CONTAINS",
                "attrs": {},
            })

    # 2-2) CONTAINS: Part → Criterion, Criterion → Item
    for parser in parsers:
        for cycle, crit_dict, group in parser.iter_criteria():
            crit_num = str(crit_dict.get("criterion", ""))
            c_id = criterion_id(cycle, parser.PART_KEY, crit_num)
            edges.append({
                "source": f"part_{parser.PART_KEY}",
                "target": c_id,
                "type": "CONTAINS",
                "attrs": {"cycle": cycle},
            })
            for parsed_item in parser.iter_items(cycle, crit_dict, group):
                i_id = item_id(cycle, parser.PART_KEY, crit_num, parsed_item["item_key"])
                edges.append({
                    "source": c_id,
                    "target": i_id,
                    "type": "CONTAINS",
                    "attrs": {},
                })

    # 2-3) group 단위 매핑 엣지 (MAPS_TO, MERGED_WITH)
    #      파일 내부에 그룹이 동일 번호로 5개 파일 모두 들어있으므로
    #      파일(part)별로 독립적으로 엣지를 만든다 (파트 간에는 매핑하지 않음).
    for parser in parsers:
        for group in parser.iter_groups():
            edges.extend(build_group_edges(parser.PART_KEY, group))

    # 2-4) ITEM_MAPS_TO: item 수준 mapping_note → 자동 추론
    item_edge_count = 0
    for parser in parsers:
        for cycle, crit_dict, group in parser.iter_criteria():
            crit_num = str(crit_dict.get("criterion", ""))
            for parsed_item in parser.iter_items(cycle, crit_dict, group):
                note = parsed_item.get("mapping_note")
                if not note:
                    continue
                src_id = item_id(cycle, parser.PART_KEY, crit_num, parsed_item["item_key"])
                new_edges = build_item_mapping_edges(
                    src_id,
                    parser.PART_KEY,
                    cycle,
                    note,
                    node_index,
                )
                edges.extend(new_edges)
                item_edge_count += len(new_edges)

    # ------------------------------------------------------------------
    # 3) embeddings.json (임베딩은 사용자 PC 에서 실행)
    # ------------------------------------------------------------------
    # Criterion 과 Item 의 텍스트를 임베딩 대상으로 삼는다.
    embed_targets: List[Dict[str, Any]] = []
    for n in nodes:
        if n["type"] == "Criterion":
            text_parts = [n["attrs"].get("title", "")]
            # 개요의 Criterion 은 content 를 title 과 함께 묶어 임베딩하는 게 자연스럽지만
            # Item 으로 이미 분리 저장되므로 Criterion 은 title 만 embed.
            text = " / ".join(t for t in text_parts if t).strip()
            if not text:
                continue
            embed_targets.append({
                "node_id": n["id"],
                "kind": "Criterion",
                "text": text,
            })
        elif n["type"] == "Item":
            text = (n["attrs"].get("text") or "").strip()
            if not text:
                continue
            embed_targets.append({
                "node_id": n["id"],
                "kind": "Item",
                "text": text,
            })

    embeddings_payload = {
        "model_name": "paraphrase-multilingual-MiniLM-L12-v2",
        "vector_dim": None,        # 모델 로드 후 채움
        "normalize": True,
        "tfidf_dim": None,         # TF-IDF fit 후 채움
        "built_at": None,          # 사용자가 build_embeddings.py 실행 시 기록
        "targets": embed_targets,  # {node_id, kind, text}
        "vectors": {},             # node_id → [float, ...]
        "tfidf_vectors": {},       # node_id → [float, ...]  (보조)
        "similar_edges": [],       # [{source, target, score_dense, score_tfidf, score_hybrid}]
        "notes": (
            "이 파일은 build_graph.py 가 빌드 시점에 '임베딩 대상'만 채워 둔 것입니다. "
            "사용자는 자신의 PC에서 build_embeddings.py 를 실행해 vectors/tfidf_vectors/similar_edges 를 채우고 "
            "필요 시 graph_edges.json 의 SIMILAR_TO 엣지로 병합할 수 있습니다."
        ),
    }

    # ------------------------------------------------------------------
    # 4) meta.json
    # ------------------------------------------------------------------
    node_type_counts = Counter(n["type"] for n in nodes)
    edge_type_counts = Counter(e["type"] for e in edges)

    # 파트별 그룹 수 / mapping_type 분포
    per_part_stats: Dict[str, Any] = {}
    for parser in parsers:
        mt_counter = Counter()
        crit4 = 0
        crit3 = 0
        item_cnt = 0
        isolated_cycle3 = 0  # 4주기에 매핑되지 않는 3주기 노드 수
        for group in parser.iter_groups():
            mt_counter[group.get("mapping_type", "")] += 1
            c4 = group.get("cycle_4")
            has_c4 = isinstance(c4, dict) and c4
            if has_c4:
                crit4 += 1
            for c3 in group.get("cycle_3") or []:
                if isinstance(c3, dict):
                    crit3 += 1
                    if not has_c4:
                        isolated_cycle3 += 1
        # item count
        for _c, crit_dict, group in parser.iter_criteria():
            for _it in parser.iter_items(_c, crit_dict, group):
                item_cnt += 1
        per_part_stats[parser.PART_KEY] = {
            "label": parser.PART_LABEL,
            "source_file": parser.SOURCE_FILE,
            "criterion_4_count": crit4,
            "criterion_3_count": crit3,
            "item_count": item_cnt,
            "mapping_type_dist": dict(mt_counter),
            "isolated_cycle3_criterion_count": isolated_cycle3,
        }

    # 전체 mapping_type 집합
    all_mapping_types = sorted({
        mt for stats in per_part_stats.values() for mt in stats["mapping_type_dist"]
    })

    meta = {
        "version": "phase2.v1",
        "built_at": datetime.now().isoformat(timespec="seconds"),
        "schema": {
            "node_types": ["Cycle", "Part", "Criterion", "Item"],
            "edge_types": [
                "CONTAINS",
                "MAPS_TO",
                "MERGED_WITH",
                "SPLIT_INTO",
                "MOVED_TO",
                "ITEM_MAPS_TO",
                "SIMILAR_TO",
            ],
            "id_patterns": {
                "Cycle": "cycle_{3|4}",
                "Part": "part_{overview|report|evidence|checkpoints|notes}",
                "Criterion": "crit_{cycle}_{part_key}_{criterion_number}",
                "Item": "item_{cycle}_{part_key}_{criterion_number}_{item_key}",
            },
        },
        "totals": {
            "nodes": len(nodes),
            "edges": len(edges),
            "nodes_by_type": dict(node_type_counts),
            "edges_by_type": dict(edge_type_counts),
            "item_maps_to_edges": item_edge_count,
            "embed_targets": len(embed_targets),
        },
        "per_part": per_part_stats,
        "mapping_type_system": {
            "base_types": ["유지", "수정", "통합", "분할", "이동", "신설", "삭제"],
            "cardinality": ["1:1", "N:1", "1:N"],
            "observed": all_mapping_types,
            "note": (
                "주요점검사항 파일의 '변경됨 (1:1)'은 Phase 1 검수에서 '수정 (1:1)' 또는 '유지 (1:1)'로 통일됨. "
                "원본은 각 그룹의 mapping_type_original 필드에 보존 (존재하는 경우)."
            ),
        },
        "limitations": [
            "ITEM_MAPS_TO 엣지는 mapping_note 에서 '4주기 X.Y itemN' 패턴을 자동 파싱한 경우에만 생성. "
            "자연어로만 기술된 매핑(예: '4주기에서 삭제됨')은 노드 attrs.mapping_note 에만 보존.",
            "SPLIT_INTO/MOVED_TO 는 group_id 단위로는 완전 표현 불가(한 group 이 여러 4주기 준거를 가리키는 구조가 아니어서). "
            "이 정보는 MAPS_TO 엣지의 attrs.mapping_base / attrs.mapping_type 으로만 표기됨.",
            "SIMILAR_TO 엣지는 사용자 PC의 build_embeddings.py 실행으로 생성됨. 기본 그래프에는 없음.",
            "삭제된 3주기 항목(4주기에 매핑 없음)은 MAPS_TO 엣지 없이 고립 노드로 남음.",
        ],
    }

    # ------------------------------------------------------------------
    # 5) 저장
    # ------------------------------------------------------------------
    save_json(os.path.join(output_dir, "graph_nodes.json"), {"nodes": nodes})
    save_json(os.path.join(output_dir, "graph_edges.json"), {"edges": edges})
    save_json(os.path.join(output_dir, "embeddings.json"), embeddings_payload)
    save_json(os.path.join(output_dir, "graph_meta.json"), meta)

    return {
        "nodes": len(nodes),
        "edges": len(edges),
        "item_maps_to_edges": item_edge_count,
        "embed_targets": len(embed_targets),
        "output_dir": output_dir,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input-dir", required=True)
    ap.add_argument("--output-dir", required=True)
    args = ap.parse_args()
    result = build(args.input_dir, args.output_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
