"""공통 파서 인터페이스 + PART 레지스트리.

각 파일(개요/보고서/근거자료/점검사항/유의사항)은 BaseParser 를 상속한
구체 파서 클래스로 처리된다. 새 파일/섹션이 추가되어도 이 파일을 수정할 필요가 없고
해당 Parser 클래스만 새로 작성 후 PART_REGISTRY 에 등록하면 된다.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Iterable, List, Tuple


class BaseParser(ABC):
    """5개 파일 각각의 파싱 인터페이스."""

    #: Part 식별자 (예: 'overview', 'evidence'). 노드 ID 생성에 사용됨.
    PART_KEY: str = ""
    #: 사용자에게 보여줄 Part 이름 (예: '편람 개요 비교').
    PART_LABEL: str = ""
    #: 원본 파일 이름.
    SOURCE_FILE: str = ""

    def __init__(self, data: List[dict]):
        self.data = data

    # ---- 그룹 이터레이션 -------------------------------------------------
    def iter_groups(self) -> Iterable[dict]:
        """group_id, theme, mapping_type, mapping_note, cycle_4, cycle_3 을 갖는 group dict."""
        return iter(self.data)

    # ---- Criterion 추출 --------------------------------------------------
    def iter_criteria(self) -> Iterable[Tuple[str, dict, dict]]:
        """(cycle, criterion_dict, group_dict) 순차 생성.

        cycle: "3" or "4"
        """
        for g in self.iter_groups():
            # cycle_4 는 dict, cycle_3 는 list 로 통일되어 있음
            c4 = g.get("cycle_4")
            if isinstance(c4, dict) and c4:
                yield ("4", c4, g)
            for c in g.get("cycle_3") or []:
                if isinstance(c, dict):
                    yield ("3", c, g)

    # ---- Item 추출 (파일마다 달라서 서브클래스가 구현) --------------------
    @abstractmethod
    def iter_items(self, cycle: str, criterion: dict, group: dict) -> Iterable[Dict[str, Any]]:
        """각 Criterion 아래 항목(Item)들을 dict 형태로 생성.

        반환되는 dict는 최소한 다음 필드를 포함해야 한다:
            - item_key: 해당 Criterion 내 고유 식별자 (ID 생성에 사용)
            - text: 임베딩/검색에 사용할 주 텍스트
            - raw: 원본 attrs (노드 속성에 그대로 복사)
        선택 필드:
            - mapping_note: item 수준 mapping_note
            - subfield: 근거자료의 '정보공시' 등 서브필드명
            - sub_items: 리스트(점검사항의 sub_items)
        """


#: 파서 구현체가 등록될 레지스트리.
PART_REGISTRY: Dict[str, type] = {}


def register_part(cls):
    """데코레이터: 파서 클래스를 PART_REGISTRY 에 등록."""
    if not cls.PART_KEY:
        raise ValueError(f"{cls.__name__} must define PART_KEY")
    PART_REGISTRY[cls.PART_KEY] = cls
    return cls
