"""사용자 PC 에서 실행하는 임베딩 생성 스크립트.

입력: graph_nodes.json, graph_edges.json, embeddings.json (build_graph.py 산출물)
동작:
  1) embeddings.json['targets'] 의 각 텍스트에 대해
     - Sentence-Transformers (paraphrase-multilingual-MiniLM-L12-v2) 로 밀집 벡터 생성
     - TF-IDF 로 희소 벡터 생성 (sparse 유지, 디스크에는 저장하지 않음)
  2) 하이브리드 점수 = alpha * dense_cos + (1 - alpha) * tfidf_cos 로 similar_edges 산출
  3) embeddings.json 에 vectors(=dense), similar_edges, hyperparams, tfidf 메타정보 채움
     - TF-IDF 개별 벡터는 JSON에 저장하지 않는다 (파일 크기 방지).
     - 재현성을 위해 vocabulary/idf 등의 메타만 기록.
  4) (옵션) --merge-edges 지정 시 graph_edges.json 에 SIMILAR_TO 엣지 병합 저장

사용 예:
    python build_embeddings.py \
        --input-dir ./output \
        --top-k 5 --threshold 0.55 --alpha 0.7 --all-pairs --merge-edges
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from typing import Any, Dict, List, Tuple

try:
    import numpy as np
except ImportError as e:  # pragma: no cover
    raise SystemExit(
        "numpy 가 설치되어 있지 않습니다. `pip install numpy` 후 다시 실행해 주세요."
    ) from e


MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"
TFIDF_MAX_FEATURES = 5000


def load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: str, data: Any) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# --------------------------------------------------------------------------
# Sentence-Transformers: dense 임베딩
# --------------------------------------------------------------------------

def load_model():
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as e:  # pragma: no cover
        raise SystemExit(
            "sentence-transformers 가 설치되어 있지 않습니다. "
            "`pip install sentence-transformers` 후 다시 실행해 주세요."
        ) from e
    print(f"[1/4] 모델 로드: {MODEL_NAME}")
    return SentenceTransformer(MODEL_NAME)


def encode_dense(model, texts: List[str], batch_size: int = 64) -> np.ndarray:
    print(f"[2/4] 밀집 임베딩 생성: {len(texts)}개 텍스트")
    emb = model.encode(
        texts,
        batch_size=batch_size,
        convert_to_numpy=True,
        show_progress_bar=True,
        normalize_embeddings=True,
    )
    return emb.astype(np.float32)


# --------------------------------------------------------------------------
# TF-IDF (sparse 유지)
# --------------------------------------------------------------------------

def encode_tfidf_sparse(texts: List[str]):
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.preprocessing import normalize
    except ImportError as e:  # pragma: no cover
        raise SystemExit(
            "scikit-learn 이 설치되어 있지 않습니다. `pip install scikit-learn` 후 다시 실행해 주세요."
        ) from e
    print(f"[3/4] TF-IDF 벡터 생성: {len(texts)}개 텍스트 (char 2~4 ngram, max_features={TFIDF_MAX_FEATURES})")
    vec = TfidfVectorizer(
        analyzer="char_wb",
        ngram_range=(2, 4),
        min_df=1,
        max_df=0.95,
        max_features=TFIDF_MAX_FEATURES,
    )
    X = vec.fit_transform(texts)       # CSR sparse
    X = normalize(X, norm="l2", axis=1, copy=False)
    return X, vec


# --------------------------------------------------------------------------
# 하이브리드 유사도 → SIMILAR_TO 엣지
# --------------------------------------------------------------------------

def cycle_of(node_id: str) -> str:
    """node_id 에서 cycle(3|4)을 추출. 없으면 ''."""
    if node_id.startswith("cycle_"):
        return node_id.split("_", 1)[1]
    parts = node_id.split("_")
    if parts[0] in ("crit", "item") and len(parts) > 1:
        return parts[1]
    return ""


def build_similar_edges(
    node_ids: List[str],
    kinds: List[str],
    dense: np.ndarray,
    tfidf_sparse,
    alpha: float,
    top_k: int,
    threshold: float,
    cross_cycle_only: bool,
) -> List[Dict[str, Any]]:
    """하이브리드 cos 유사도 → top-k SIMILAR_TO 엣지 (쌍당 한 번, source<target 기준)."""
    print(
        f"[4/4] SIMILAR_TO 엣지 계산 "
        f"(alpha={alpha}, top_k={top_k}, threshold={threshold}, cross_cycle_only={cross_cycle_only})"
    )
    n = len(node_ids)
    # dense cos (이미 L2 normalize 되어있음)
    dense_sim = dense @ dense.T  # (n, n) float32

    # sparse tfidf cos: (n, V) @ (V, n) → (n, n) dense. 메모리: n*n*4B.
    # 1,569^2 * 4 = 약 10MB 수준이므로 OK.
    tfidf_sim = (tfidf_sparse @ tfidf_sparse.T).toarray().astype(np.float32)

    hybrid = alpha * dense_sim + (1 - alpha) * tfidf_sim
    # 자기자신 제외
    np.fill_diagonal(hybrid, -1.0)

    # cross_cycle_only 이면 같은 cycle 쌍은 -1 로 마스킹
    if cross_cycle_only:
        cycles = np.array([cycle_of(nid) for nid in node_ids])
        same_cycle = cycles[:, None] == cycles[None, :]
        hybrid = np.where(same_cycle, -1.0, hybrid)

    edges: List[Dict[str, Any]] = []
    # 한 쌍에 대해 source<target 순으로만 저장 (무방향 해석 가정)
    # 각 노드 기준 top_k 를 뽑되, 중복 쌍은 skip
    seen_pairs: set = set()
    for i in range(n):
        scores = hybrid[i]
        if top_k >= n:
            order = np.argsort(-scores)
        else:
            # argpartition 으로 top_k 후보 추출 후 정렬
            order = np.argpartition(-scores, top_k)[:top_k]
            order = order[np.argsort(-scores[order])]
        for j in order:
            if j == i:
                continue
            s = float(scores[j])
            if s < threshold:
                continue
            a, b = (i, j) if i < j else (j, i)
            key = (a, b)
            if key in seen_pairs:
                continue
            seen_pairs.add(key)
            edges.append({
                "source": node_ids[a],
                "target": node_ids[b],
                "type": "SIMILAR_TO",
                "attrs": {
                    "score_hybrid": round(s, 4),
                    "score_dense": round(float(dense_sim[a, b]), 4),
                    "score_tfidf": round(float(tfidf_sim[a, b]), 4),
                    "kind_pair": f"{kinds[a]}-{kinds[b]}",
                },
            })
    # 점수 내림차순 정렬
    edges.sort(key=lambda e: -e["attrs"]["score_hybrid"])
    return edges


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input-dir", required=True, help="graph_*.json, embeddings.json 위치")
    ap.add_argument("--top-k", type=int, default=5)
    ap.add_argument("--threshold", type=float, default=0.55)
    ap.add_argument("--alpha", type=float, default=0.7, help="dense 가중치 (TF-IDF = 1-alpha)")
    ap.add_argument("--all-pairs", action="store_true",
                    help="동일 cycle 간 SIMILAR_TO 도 생성 (기본은 3주기↔4주기만)")
    ap.add_argument("--merge-edges", action="store_true",
                    help="graph_edges.json 에 SIMILAR_TO 엣지 병합 저장")
    args = ap.parse_args()

    input_dir = args.input_dir
    emb_path = os.path.join(input_dir, "embeddings.json")
    edges_path = os.path.join(input_dir, "graph_edges.json")
    if not os.path.exists(emb_path):
        sys.exit(f"[ERROR] 파일 없음: {emb_path}")
    if not os.path.exists(edges_path):
        sys.exit(f"[ERROR] 파일 없음: {edges_path}")

    emb_doc = load_json(emb_path)
    targets = emb_doc.get("targets") or []
    if not targets:
        sys.exit("[ERROR] embeddings.json 에 targets 가 비어있습니다.")

    node_ids = [t["node_id"] for t in targets]
    kinds = [t["kind"] for t in targets]
    texts = [t["text"] for t in targets]

    # 1) dense
    model = load_model()
    dense = encode_dense(model, texts)
    vector_dim = int(dense.shape[1])

    # 2) TF-IDF sparse
    tfidf_sparse, tfidf_vectorizer = encode_tfidf_sparse(texts)

    # 3) SIMILAR_TO
    sim_edges = build_similar_edges(
        node_ids=node_ids,
        kinds=kinds,
        dense=dense,
        tfidf_sparse=tfidf_sparse,
        alpha=args.alpha,
        top_k=args.top_k,
        threshold=args.threshold,
        cross_cycle_only=not args.all_pairs,
    )

    # 4) embeddings.json 갱신 — dense 벡터만 저장, TF-IDF 개별 벡터는 저장하지 않음
    emb_doc["vector_dim"] = vector_dim
    emb_doc["tfidf_dim"] = int(tfidf_sparse.shape[1])
    emb_doc["tfidf_max_features"] = TFIDF_MAX_FEATURES
    emb_doc["built_at"] = datetime.now().isoformat(timespec="seconds")
    emb_doc["vectors"] = {nid: dense[i].tolist() for i, nid in enumerate(node_ids)}
    # 용량 이유로 저장하지 않음. 필요 시 이 스크립트 재실행으로 재구성 가능.
    emb_doc["tfidf_vectors_stored"] = False
    emb_doc["similar_edges"] = sim_edges
    emb_doc["hyperparams"] = {
        "alpha": args.alpha,
        "top_k": args.top_k,
        "threshold": args.threshold,
        "cross_cycle_only": not args.all_pairs,
    }
    save_json(emb_path, emb_doc)
    print(f"→ embeddings.json 업데이트 완료 (SIMILAR_TO {len(sim_edges)}개)")

    # 5) 선택적으로 graph_edges.json 에 병합
    if args.merge_edges:
        edges_doc = load_json(edges_path)
        edges_doc["edges"] = [e for e in edges_doc["edges"] if e.get("type") != "SIMILAR_TO"]
        edges_doc["edges"].extend(sim_edges)
        save_json(edges_path, edges_doc)
        print(f"→ graph_edges.json 에 SIMILAR_TO 엣지 {len(sim_edges)}개 병합")


if __name__ == "__main__":
    main()
