import json
import os
from pathlib import Path

import chromadb
import torch


# --------------------------------------------------
# 경로 / 모델 설정
# --------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[1]

KB_PATH = PROJECT_ROOT / "rag" / "policy_kb.jsonl"
VECTORDB_PATH = "/nfs/team/vectordb"
HF_CACHE_PATH = "/nfs/team/hf_cache"

MODEL_NAME = "BAAI/bge-m3"
COLLECTION_NAME = "policy_kb_bge_m3"

# config.yaml의 hf_cache 경로와 동일하게 사용
os.environ.setdefault("HF_HOME", HF_CACHE_PATH)

# HF_HOME 설정 후 import
from sentence_transformers import SentenceTransformer


_model = None
_collection = None
_index_ready = False


# --------------------------------------------------
# KB 로드
# --------------------------------------------------

def _load_kb():
    rows = []

    with open(KB_PATH, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))

    return rows


# --------------------------------------------------
# BGE-M3 로드
# --------------------------------------------------

def _get_model():
    global _model

    if _model is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"

        print(f"[RAG] BGE-M3 로드 중... device={device}")

        _model = SentenceTransformer(
            MODEL_NAME,
            device=device,
        )

        print("[RAG] BGE-M3 로드 완료")

    return _model


# --------------------------------------------------
# Chroma collection
# --------------------------------------------------

def _get_collection():
    global _collection

    if _collection is None:
        client = chromadb.PersistentClient(
            path=VECTORDB_PATH
        )

        _collection = client.get_or_create_collection(
            name=COLLECTION_NAME,
            embedding_function=None,
            configuration={
                "hnsw": {
                    "space": "cosine"
                }
            },
        )

    return _collection


# --------------------------------------------------
# Metadata 변환
# --------------------------------------------------

def _to_metadata(row):
    """
    embed_text를 제외한 KB 정보를 Chroma metadata로 저장.
    list는 JSON 문자열로 저장하여 호환성을 단순하게 유지한다.
    """

    return {
        "doc_id": row.get("doc_id", ""),
        "group": row.get("group", ""),
        "effective_date": row.get("effective_date", ""),
        "status": row.get("status", ""),
        "url": row.get("url", ""),
        "doc_name": row.get("doc_name", ""),
        "clause": row.get("clause", ""),
        "summary": row.get("summary", ""),
        "text": row.get("text", ""),
        "applies_to": json.dumps(
            row.get("applies_to", []),
            ensure_ascii=False,
        ),
        "purpose_tags": json.dumps(
            row.get("purpose_tags", []),
            ensure_ascii=False,
        ),
        "violation_types": json.dumps(
            row.get("violation_types", []),
            ensure_ascii=False,
        ),
        "updated_at": row.get("updated_at", ""),
    }


# --------------------------------------------------
# Vector DB 생성 / 갱신
# --------------------------------------------------

def build_index():
    global _index_ready

    rows = _load_kb()

    if not rows:
        raise RuntimeError("policy_kb.jsonl이 비어 있습니다.")

    model = _get_model()
    collection = _get_collection()

    # 중요:
    # 임베딩에는 embed_text만 사용
    texts = [row["embed_text"] for row in rows]

    embeddings = model.encode(
        texts,
        batch_size=8,
        show_progress_bar=True,
        normalize_embeddings=True,
    )

    ids = [row["doc_id"] for row in rows]

    metadatas = [
        _to_metadata(row)
        for row in rows
    ]

    # 기존 doc_id는 갱신하고,
    # 새로운 doc_id는 추가
    collection.upsert(
        ids=ids,
        embeddings=embeddings.tolist(),
        documents=texts,
        metadatas=metadatas,
    )

    # KB에서 삭제된 문서가 Vector DB에 남지 않도록 정리
    existing = collection.get(
        include=["metadatas"]
    )

    stale_ids = [
        doc_id
        for doc_id in existing["ids"]
        if doc_id not in set(ids)
    ]

    if stale_ids:
        collection.delete(ids=stale_ids)

    _index_ready = True

    print(
        f"[RAG] Vector DB 동기화 완료: "
        f"{collection.count()}개 문서"
    )


# --------------------------------------------------
# 필터
# --------------------------------------------------

def _match_violation(metadata, violation_types):
    if not violation_types:
        return True

    if isinstance(violation_types, str):
        violation_types = [violation_types]

    doc_types = set(
        json.loads(metadata.get("violation_types", "[]"))
    )

    requested = set(violation_types)

    return bool(doc_types & requested)


def _match_purpose(metadata, purpose):
    if purpose is None:
        return True

    doc_purposes = set(
        json.loads(metadata.get("purpose_tags", "[]"))
    )

    purpose_normalized = str(purpose).strip().lower()

    # 광고 목적:
    # 광고·홍보 정책 + 전체 정책 모두 적용
    if purpose_normalized in {
        "ad",
        "ads",
        "advertisement",
        "광고",
        "광고·홍보",
    }:
        return bool(
            doc_purposes & {"광고·홍보", "전체"}
        )

    # 정보 / 일상 / 재미 / 기타 등:
    # 현재 KB에서는 "전체" 정책 적용
    return "전체" in doc_purposes


# --------------------------------------------------
# 검색
# --------------------------------------------------

def search(
    query,
    k=3,
    violation_types=None,
    purpose=None,
):
    """
    정책 KB 검색.

    Args:
        query (str):
            검색 질문 또는 탐지 내용.

        k (int):
            반환할 evidence 개수.

        violation_types (str | list[str] | None):
            예:
            "hate"
            ["hate", "profanity"]

        purpose (str | None):
            예:
            "ad"
            "광고·홍보"
            None

    Returns:
        list[dict]:
            v0.2 evidence 형식
            {
                "doc_id": ...,
                "doc": ...,
                "clause": ...,
                "status": ...,
                "url": ...,
                "score": ...
            }
    """

    global _index_ready

    if not query or not str(query).strip():
        return []

    if k <= 0:
        return []

    if not _index_ready:
        build_index()

    model = _get_model()
    collection = _get_collection()

    query_embedding = model.encode(
        [query],
        normalize_embeddings=True,
    )[0]

    total = collection.count()

    if total == 0:
        return []

    # 필터를 Python에서 적용하기 때문에
    # 먼저 전체 문서를 vector similarity 순으로 가져온다.
    result = collection.query(
        query_embeddings=[
            query_embedding.tolist()
        ],
        n_results=total,
        include=[
            "metadatas",
            "distances",
        ],
    )

    metadatas = result["metadatas"][0]
    distances = result["distances"][0]

    evidence = []

    for metadata, distance in zip(
        metadatas,
        distances,
    ):
        if not _match_violation(
            metadata,
            violation_types,
        ):
            continue

        if not _match_purpose(
            metadata,
            purpose,
        ):
            continue

        # cosine distance -> cosine similarity
        score = 1.0 - float(distance)

        evidence.append({
            "doc_id": metadata["doc_id"],
            "doc": metadata["doc_name"],
            "clause": metadata["clause"],
            "status": metadata["status"],
            "url": metadata["url"],
            "score": round(score, 4),
        })

        if len(evidence) >= k:
            break

    return evidence


# --------------------------------------------------
# 직접 실행 시 간단 확인
# --------------------------------------------------

if __name__ == "__main__":
    build_index()

    print("\n[RAG] 기본 검색 테스트")

    results = search(
        "협찬을 받고 작성한 광고인데 광고 표시가 없습니다.",
        k=3,
        violation_types="missing_disclosure",
        purpose="ad",
    )

    print(
        json.dumps(
            results,
            ensure_ascii=False,
            indent=2,
        )
    )