# Phase 3 — 3주기·4주기 편람 비교 대시보드 (MVP)

Phase 2 Graph RAG 산출물(`graph_nodes.json` / `graph_edges.json`)을 입력으로
**매핑 탐색 + 영향도 분석** 두 개의 탭으로 구성된 단일 HTML 대시보드.

- 단일 HTML: `dashboard.html`
- 데이터   : `data/nodes.json`, `data/edges.json`, `data/meta.json`
- 서버    : `serve.py` (CORS 우회용 로컬 HTTP 서버)
- 기술 스택: D3.js v7 (CDN) + Tailwind CSS (CDN) + Vanilla JS

---

## 1. 빠른 실행

```bash
# 1) phase3_dashboard 폴더로 이동 (이미 옮겨진 경우)
cd "최종작업(20260417)/phase3_dashboard"

# 2) 로컬 서버 실행 — 표준 라이브러리만 사용 (venv 활성화 불필요)
python serve.py
# → http://127.0.0.1:8000/dashboard.html 자동 오픈

# 옵션
python serve.py --port 9000
python serve.py --no-open       # 브라우저 자동 실행 끄기
```

> **file:// 로 열면 `fetch("data/nodes.json")` 이 CORS 로 막혀 빈 화면이 됩니다.**
> 반드시 `python serve.py` 로 띄운 뒤 `http://127.0.0.1:8000/dashboard.html` 로 접속.

### venv 활용 시 (선택)
Phase 2 에서 만들어둔 venv 를 써도 되지만, 이 대시보드는 Python 표준 라이브러리만 쓰므로
시스템 `python3` 만 있어도 동작합니다.

```bash
source "/Users/mortarteam81/Downloads/01_대학기관평가인증/최종작업(20260417)/.venv/bin/activate"
cd "./phase3_dashboard"
python serve.py
```

---

## 2. 화면 구성

### Tab 1 — 매핑 탐색 (기본)
| 위치 | 내용 |
|------|------|
| 좌 | 3주기 준거 목록 (편람 선택 시 해당 편람만) |
| 중 | SVG 매핑선 (MAPS_TO 확정 매핑) + MERGED_WITH (좌측 내부 곡선) |
| 우 | 4주기 준거 목록 |

- 좌·우 준거 행을 클릭 → 해당 준거가 **선택됨** (노란 배경) + 관련 준거 **강조(초록)** + 그 외 **흐려짐(dim)**
- 관련 준거 선택 시 SIMILAR_TO 후보가 **점선**으로 추가 표시 (threshold 이상만)
- 중앙 SVG 선 색상:
  - 회색 = 유지 · 파랑 = 수정 · 주황 = 통합 · 보라 = 분할 · 청록 = 이동 · 금색 = 복합형
  - 회색 점선 = MERGED_WITH, 연한 회색 점선 = SIMILAR_TO

### Tab 2 — 영향도 (상세 패널)
선택된 준거에 대해 다음 5개 섹션을 동시에 표시:

1. **① 선택 준거** — 제목, 그룹 번호/테마, 변경유형 뱃지, node id
2. **② 확정 매핑** — MAPS_TO (3→4 / 4←3) + 같은 그룹의 MERGED_WITH 자매 준거
   - 신설/삭제 후보 경고 박스도 자동 표시
3. **③ Item 수준** — 해당 준거의 하위 항목(Item) 본문 + mapping_note
   - evidence 는 subfield (정보공시/제출자료/현지확인자료/면담/방문) 별로 그룹핑
   - 자동 파싱된 `ITEM_MAPS_TO` 엣지도 함께 표시 (inferred)
4. **④ Cross-part 연결** — **같은 주기 내 다른 편람 섹션**과의 SIMILAR_TO 연결
   - "같은 주제의 준거가 5개 편람에 어디에 등장하는지" 파악
5. **⑤ SIMILAR_TO 임베딩 후보** — Criterion-Criterion, threshold 이상
   - `확정` 뱃지: 이미 MAPS_TO 에 존재
   - `신규후보` 뱃지(노란배경): MAPS_TO 에 없는 새 후보 → **검토 가치 있음**

### Tab 3 — 신구조문 대비표 (NEW)
**법령 신구조문 대비표** 형식으로 3주기↔4주기를 2-column 표로 직접 비교.

| 위치 | 내용 |
|------|------|
| 좌 (네비) | 4주기 준거 목록 — "신설·변경만" 체크박스로 필터 (기본 ON), 편람 드롭다운과 검색에 연동 |
| 우 (본문) | 선택한 4주기 준거의 2-column 표 (3주기 ← → 4주기) |

- 정렬 규칙: 4주기 items 순서대로, `(subfield + item_key)` 동일성으로 좌우 행 매칭
- 통합(N:1): 여러 3주기 준거를 한 행에 열거 + `🔗 통합(N:1)` 안내 문구
- 매칭 실패: 한쪽만 있는 행은 `(신설)` / `(삭제됨)` 셀 + 변경 배경색
- **어절 단위 diff** (공백 기준, LCS):
  - <span>추가</span> = 녹색 배경 / <span>삭제</span> = 빨강 취소선
- mapping_note 는 우측 셀 하단에 `📝` 아이콘과 함께 표시
- DOCX Export 는 다음 세션 구현 예정 (python-docx, 동일 레이아웃)

---

## 3. 전역 컨트롤

| 컨트롤 | 설명 |
|--------|------|
| 편람 드롭다운 | 5개 편람 파일 중 하나 선택 (기본: 편람 개요) |
| SIMILAR_TO ≥ 슬라이더 | 임계값 0.55 ~ 1.0 (기본 0.75) — SVG 후보선 + Tab 2 섹션 ④⑤ 에 동시 적용 |
| same-cycle 토글 | 끄면 3↔4 교차주기만 표시, 켜면 동일주기 (예: 4↔4) 도 포함 |
| 제목 검색 | 좌·우 목록을 제목/ID 로 실시간 필터 |
| 초기화 버튼 | 선택·검색 해제 |

### 키보드 단축키
- `1` → Tab 1 / `2` → Tab 2 / `3` → Tab 3 (신구조문 대비표)
- `Esc` → 선택 해제 (Tab 1 선택 + Tab 3 선택 모두)

---

## 4. 폴더 구조

```
phase3_dashboard/
├── dashboard.html    # 단일 HTML (D3 + Tailwind CDN + Vanilla JS)
├── serve.py          # 로컬 HTTP 서버 (표준 라이브러리만)
├── README.md         # 본 문서
└── data/
    ├── nodes.json    # 1,576 노드 (Cycle·Part·Criterion·Item)
    ├── edges.json    # 7,064 엣지 (CONTAINS 1604 / MAPS_TO 160 / MERGED 43 / ITEM_MAPS_TO 160 / SIMILAR_TO 5097)
    └── meta.json     # 스키마 · part 별 집계 · mapping_type 분포
```

---

## 5. 데이터 갱신 방법

Phase 2 산출물이 갱신되면:

```bash
# 방법 A — 직접 복사
cp ../phase2_graphrag/output/graph_nodes.json ./data/nodes.json
cp ../phase2_graphrag/output/graph_edges.json ./data/edges.json
cp ../phase2_graphrag/output/graph_meta.json  ./data/meta.json

# 방법 B — 심볼릭 링크 (macOS/Linux)
ln -sf "$(pwd)/../phase2_graphrag/output/graph_nodes.json" ./data/nodes.json
ln -sf "$(pwd)/../phase2_graphrag/output/graph_edges.json" ./data/edges.json
ln -sf "$(pwd)/../phase2_graphrag/output/graph_meta.json"  ./data/meta.json
```

브라우저에서 **하드 리프레시** (`⌘+Shift+R` 또는 `Ctrl+Shift+R`) 후 적용.
(`serve.py` 는 `Cache-Control: no-store` 를 내려 일반 새로고침만으로도 대부분 반영됩니다.)

---

## 6. 한계 및 주의사항

1. **Tab 3 신구조문 대비표** — 구현 완료. DOCX Export 는 다음 세션.
2. **단일 편람 필터 전용** — 한 번에 한 편람만 보기. 다중 편람 비교는 Tab 2 의 Cross-part 섹션으로 대체.
   - 다중 체크박스는 Phase 3.5 확장으로 예정.
3. **SVG 매핑선은 DOM 좌표 기반** — 리스트 스크롤/리사이즈 시 debounce 로 재렌더.
   매우 빠른 연속 스크롤에서는 짧은 순간 라인이 어긋나 보일 수 있음.
4. **SIMILAR_TO 는 "후보"** — 점선 + 투명도 낮춤으로 시각적 구분. 법·제도 용어의 미세한 수치 차이는
   임베딩 모델이 놓칠 수 있음. 최종 판단은 사람 검토 필수.
5. **localStorage 미사용** — 탭·선택·필터 상태는 새로고침 시 초기화됨 (의도된 제약).
6. **Tailwind CDN, D3 CDN** — 인터넷 필요. 오프라인 환경에서 쓰려면 두 파일을
   로컬에 받아 `<script>` 경로를 교체.

---

## 7. 트러블슈팅

| 증상 | 원인 / 해결 |
|------|------|
| 빈 화면 + "데이터 로드 실패" | `python serve.py` 로 실행하지 않았을 가능성. `http://127.0.0.1:8000/dashboard.html` 로 접속했는지 확인. |
| "Address already in use" | 다른 포트 사용: `python serve.py --port 9000` |
| Tailwind/D3 가 로드 안 됨 | 사내망에서 CDN 차단된 경우 — 회사 프록시 설정 또는 CDN 파일 로컬화 필요. |
| 매핑선이 어긋나 보임 | 창 크기 조절 후 자동 재렌더. 여전히 어긋나면 새로고침(`⌘+R`). |
| 한글 폰트가 깨짐 | 시스템 폰트(Apple SD Gothic Neo / Noto Sans KR) 가 없으면 sans-serif 로 fallback. |

---

## 8. 다음 단계 (Phase 3.5 / 4)

- **DOCX Export (Tab 3)** — `python-docx` 로 법령 대비표 양식(2-column 표) 출력. 부서별 회의자료 배포용.
- Phase 4 전체 구조 Sankey (편람별 흐름) · Chord (그룹 간 통합/이동 연결)
- 다중 편람 체크박스: "개요 + 점검사항" 같이 2~3개 동시 비교
- Export: 영향도 패널을 PDF / DOCX 로 저장 (연말 실적보고 연계)
- IR 시스템 연계: 확정 매핑 기반 증빙자료 재설계 체크리스트 자동 생성
