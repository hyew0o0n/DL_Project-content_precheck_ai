"""정책 DB 구글 시트 → rag/policy_kb.jsonl

실행 (프로젝트 최상위 폴더에서)
    python rag/build_kb.py
    python -m rag.search        # 바뀐 행만 다시 임베딩 → "N개 문서" 확인

[W8 수정]
- 시트 헤더가 조금 바뀌어도(띄어쓰기·'/'·괄호 차이, 이름 일부 변경) 키워드로 찾아서 맞춤
- 필수 열을 못 찾으면 실제 시트 헤더를 보여주고 멈춤 (예전엔 KeyError: 'clause')
- 결과를 항상 rag/policy_kb.jsonl에 씀 (예전엔 실행한 폴더에 써서 프로젝트 최상위에 파일이 생겼음)
- doc_id 빈칸·중복 검사
"""
import json
import re
import sys
from pathlib import Path

import pandas as pd

SHEET_ID = "14CZsLuvHyw-6b-SwTY_GkbOCHEfDLPJA33NWQkhz4YQ"
URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&gid=0"
OUT_PATH = Path(__file__).resolve().parent / "policy_kb.jsonl"

# JSON 키 → 시트 헤더 후보 (앞에서부터, 띄어쓰기·기호 무시하고 '포함'되면 일치)
COLS = {
    "doc_id":          ["doc_id", "docid"],
    "group":           ["구분"],
    "effective_date":  ["시행일"],
    "status":          ["상태"],
    "url":             ["링크", "url"],
    "doc_name":        ["문서명/정책명", "문서명", "정책명"],
    "clause":          ["관련조항/세부항목", "관련조항", "세부항목", "조항"],
    "summary":         ["요약내용", "요약"],
    "text":            ["주요제재및검수대상내용", "검수대상내용", "주요제재", "본문"],
    "applies_to":      ["적용대상"],
    "purpose_tags":    ["목적태그", "목적"],
    "violation_types": ["위반유형"],
    "updated_at":      ["수정일"],
}
REQUIRED = ["doc_id", "doc_name", "clause", "summary", "text", "violation_types"]
LIST_COLS = ["applies_to", "purpose_tags", "violation_types"]


def _norm(s: str) -> str:
    """띄어쓰기·괄호·따옴표 제거, 소문자 → 헤더 비교용."""
    return re.sub(r"[\s()\[\]·:'\"]", "", str(s)).lower()


def match_columns(headers: list[str]) -> dict:
    """{시트 헤더: JSON 키}. 후보 순서대로, 아직 안 쓴 헤더 중 처음 맞는 것."""
    normed = {h: _norm(h) for h in headers}
    used, mapping = set(), {}
    for key, cands in COLS.items():
        for cand in cands:
            c = _norm(cand)
            hit = next((h for h in headers if h not in used and normed[h] == c), None) \
                or next((h for h in headers if h not in used and c in normed[h]), None)
            if hit:
                mapping[hit] = key
                used.add(hit)
                break
    return mapping


def main():
    df = pd.read_csv(URL, dtype=str).fillna("")
    headers = list(df.columns)
    mapping = match_columns(headers)

    missing = [k for k in REQUIRED if k not in mapping.values()]
    if missing:
        print("❌ 시트에서 필요한 열을 못 찾았어요:", missing)
        print("   시트 실제 헤더:", headers)
        print("   → rag/build_kb.py 위쪽 COLS의 후보에 실제 헤더 이름을 추가하세요.")
        sys.exit(1)
    print("열 매칭:", {v: k for k, v in mapping.items()})

    df = df[list(mapping)].rename(columns=mapping)
    rows, seen, problems = [], set(), []
    for r in df.to_dict("records"):
        r = {k: str(v).strip() for k, v in r.items()}
        if not (r.get("text") or r.get("summary")):
            continue  # 본문/요약이 없는 빈 행 건너뜀
        if not r.get("doc_id"):
            problems.append(f"doc_id 빈칸: {r.get('doc_name', '')[:30]}")
            continue
        if r["doc_id"] in seen:
            problems.append(f"doc_id 중복: {r['doc_id']}")
            continue
        seen.add(r["doc_id"])
        for k in COLS:
            r.setdefault(k, "")
        for c in LIST_COLS:   # 쉼표로 나눈 리스트
            r[c] = [t.strip() for t in re.split(r"[,，]", r.get(c, "")) if t.strip()]
        r["embed_text"] = f"{r['doc_name']} {r['clause']}\n{r['summary']}\n{r['text']}"
        rows.append(r)

    if problems:
        print("⚠️ 건너뛴 행:", *problems, sep="\n   ")
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"✅ {OUT_PATH.relative_to(OUT_PATH.parents[1])} 변환 완료: 정책 {len(rows)}개")


if __name__ == "__main__":
    main()
