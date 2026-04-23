# Phase 2 — Graph RAG 데이터 구축

3주기·4주기 대학기관평가인증편람 비교(검수완료) 5개 JSON 을 입력으로 받아
**계층 트리 + 매핑 엣지**로 구성된 그래프 데이터(JSON 4종)를 생성한다.
Phase 3 대시보드와 향후 RAG 검색 파이프라인의 입력이 된다.

## 1. 산출물 (`phase2_out/`)

| 파일 | 설명 |
|------|------|
| `graph_nodes.json` | `{ nodes: [ { id, type, attrs } ] }` — Cycle / Part / Criterion / Item 노드 |
| `graph_edges.json` | `{ edges: [ { source, target, type, attrs } ] }` — CONTAINS / MAPS_TO / MERGED_WITH / ITEM_MAPS_TO / (선택) SIMILAR_TO |
| `embeddings.json` | 임베딩 대상 텍스트 목록과 빈 vector 필드(사용자 PC 에서 채움) + similar_edges |
| `graph_meta.json` | 스키마 정의, 노드/엣지 집계, mapping_type 체계, 한계점 |

### 노드 ID 패턴
```
cycle_{3|4}
part_{overview|report|evidence|checkpoints|notes}
crit_{cycle}_{part_key}_{criterion_number}
item_{cycle}_{part_key}_{criterion_number}_{item_key}
```

### 엣지 타입
- `CONTAINS` — 계층(Cycle→Part→Criterion→Item)
- `MAPS_TO` — 3주기 Criterion → 4주기 Criterion (mapping_type, mapping_note 동반)
- `MERGED_WITH` — 동일 group 내 3주기 Criterion 사이(통합 케이스)
- `ITEM_MAPS_TO` — item 수준 mapping_note 자동 파싱 결과 (보수적; 실패 시 note 만 attrs 로 보존)
- `SIMILAR_TO` — (옵션) 임베딩 기반 상위-k 하이브리드 유사도 엣지

## 2. 그래프 빌드 실행

```bash
python build_graph.py \
  --input-dir "최종작업(20260417)" \
  --output-dir "phase2_out"
```

Python 표준 라이브러리만 사용하므로 추가 의존성 없이 실행 가능하다.

## 3. 임베딩 생성 (사용자 PC)

임베딩은 네트워크·용량 제약 때문에 사용자 PC 에서 별도 실행한다.

### 설치 (이미 설정한 venv 기준)
```bash
# 가상환경 활성화
source "/Users/mortarteam81/Downloads/01_대학기관평가인증/최종작업(20260417)/.venv/bin/activate"

# 필수 패키지 (설치 완료 기준):
#   sentence-transformers==2.2.2, transformers==4.30.2, tokenizers==0.13.3,
#   huggingface-hub==0.14.1, numpy 2.4.4, scikit-learn 1.8.0
# 미설치 시: pip install -r requirements.txt
```

### 실행 (권장 커맨드)
```bash
# 작업 폴더로 이동 후 실행
cd "/Users/mortarteam81/Downloads/01_대학기관평가인증/최종작업(20260417)/phase2_graphrag"

python build_embeddings.py \
  --input-dir ./output \
  --top-k 5 --threshold 0.55 --alpha 0.7 \
  --all-pairs \
  --merge-edges
```

플래그 설명:
- `--alpha 0.7`: dense 가중치. 보조 TF-IDF = 1-alpha.
- `--top-k 5`: 각 노드당 저장할 최상위 유사 엣지 수.
- `--threshold 0.55`: 하이브리드 유사도 임계값. 결과가 적으면 0.45 로 낮춰볼 것.
- `--all-pairs`: 동일 cycle 간 SIMILAR_TO 도 포함 (현 프로젝트에서는 권장).
- `--merge-edges`: SIMILAR_TO 엣지를 `graph_edges.json` 에도 병합.

### 실행 후 예상 동작
1. `paraphrase-multilingual-MiniLM-L12-v2` 모델이 이미 로컬에 있으므로 재다운로드 없음
2. 1,569 개 텍스트 → dense 384-dim 벡터 생성 (CPU 에서 약 1~3 분)
3. TF-IDF (char 2~4 gram, max_features=5000) sparse 벡터 생성 (수 초)
4. 하이브리드 cos 유사도 계산 (1569×1569 행렬, ~10MB, 수 초)
5. 각 노드당 top-5 중 threshold 이상 쌍을 SIMILAR_TO 엣지로 저장

### 실행 후 갱신되는 파일
- `output/embeddings.json`:
  - `vectors` (dense 만), `similar_edges`, `hyperparams`, `vector_dim`, `tfidf_dim`, `built_at` 채워짐
  - TF-IDF 개별 벡터는 용량 이유로 저장하지 않음 (`tfidf_vectors_stored = false`). 필요 시 스크립트 재실행으로 재구성.
  - 예상 크기: 약 15~20 MB
- `output/graph_edges.json` (--merge-edges 지정 시):
  - 기존 SIMILAR_TO 엣지 제거 후 새로 병합 (멱등성 보장)
  - 예상 크기 증가: 약 500 KB ~ 1 MB

## 4. 프로젝트 구조

```
phase2_graphrag/
├── build_graph.py          # 메인 빌더 (5개 JSON → 4종 산출물)
├── build_embeddings.py     # 사용자 PC 에서 실행: 임베딩 + SIMILAR_TO
├── requirements.txt
├── README.md
├── parsers/
│   ├── base.py             # BaseParser, PART_REGISTRY
│   ├── overview.py
│   ├── report.py
│   ├── evidence.py         # 6개 서브필드 처리
│   ├── checkpoints.py      # sub_items 포함
│   └── notes.py
└── graph/
    ├── nodes.py            # 노드 생성 (ID 패턴)
    └── edges.py            # 엣지 생성 / mapping_type 분해 / item 자동 파싱
```

## 5. 한계점 (graph_meta.json `limitations` 참조)

1. **ITEM_MAPS_TO 자동 파싱의 한계**: `"4주기 X.Y itemN"` 패턴이 명시된 경우에만 엣지 생성. 자연어로만 기술된 것("삭제됨", "확장", "기준값 변경" 등)은 노드 `attrs.mapping_note` 에만 보존.
2. **SPLIT_INTO / MOVED_TO**: 현재 group 구조는 하나의 group 이 하나의 4주기 Criterion 을 가지는 형식이라, 한 번의 이동·분할 관계를 그래프 엣지로 완전 표현할 수 없다. MAPS_TO 의 `attrs.mapping_base` / `attrs.mapping_type` 로만 표기됨 (예: `이동·통합 (N:1)`).
3. **삭제된 3주기 항목**: 4주기에 매핑 없이 삭제된 준거는 MAPS_TO 엣지 없이 고립 노드로 남음. `graph_meta.json` 의 `per_part[*].isolated_cycle3_criterion_count` 로 확인 가능.
4. **SIMILAR_TO 엣지의 정확도**: 다국어 MiniLM 모델은 한국어 의미적 유사도에 강하나, 법·제도 용어·기준값 변경 같은 미세한 수치 차이까지는 구분 못 함. 하이브리드 TF-IDF 보조점수가 표현 유사성을 보완하지만, 검색 결과는 "후보"로 취급하고 최종 확인은 사람이 수행할 것.

## 6. Phase 3 다음 단계

`graph_nodes.json` + `graph_edges.json` (+ 필요 시 `embeddings.json`) 을 입력으로
D3.js + Tailwind 기반 단일 HTML 대시보드에서:

- 메인 탭: 좌 3주기 / 중 매핑 화살표 / 우 4주기
- 클릭 시 우측 패널: 변경 영향도 (MAPS_TO + ITEM_MAPS_TO + SIMILAR_TO 종합)
- 별도 탭: 전체 구조 Sankey / Chord
