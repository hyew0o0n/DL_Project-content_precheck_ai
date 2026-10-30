import json
import pandas as pd

SHEET_ID = "14CZsLuvHyw-6b-SwTY_GkbOCHEfDLPJA33NWQkhz4YQ"
URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&gid=0"

# 시트 헤더(한글) → JSON 키(영문) 매핑
COLS = {
    "doc_id": "doc_id",
    "구분": "group",
    "시행일": "effective_date",
    "상태": "status",
    "링크": "url",
    "문서명 / 정책명": "doc_name",
    "관련 조항 / 세부 항목": "clause",
    "요약 내용": "summary",
    "주요 제재 및 검수 대상 내용": "text",
    "적용 대상": "applies_to",
    "목적 태그": "purpose_tags",
    "위반 유형": "violation_types",
    "수정일": "updated_at",
}
LIST_COLS = ["applies_to", "purpose_tags", "violation_types"]

# 시트 읽기 및 전처리
df = pd.read_csv(URL, dtype=str).fillna("")
df = df[[c for c in COLS if c in df.columns]].rename(columns=COLS)

with open("policy_kb.jsonl", "w", encoding="utf-8") as f:
  for row in df.to_dict("records"):
    if not (row.get("text") or row.get("summary")):
      continue  # 본문/요약이 없는 빈 행 건너뜀

    # 리스트형 컬럼 파싱 (쉼표 기준 분할)
    for c in LIST_COLS:
      row[c] = [t.strip() for t in row.get(c, "").split(",") if t.strip()]

    # RAG 임베딩용 통합 텍스트 작성
    row["embed_text"] = (
        f"{row['doc_name']} {row['clause']}\n{row['summary']}\n{row['text']}"
    )

    f.write(json.dumps(row, ensure_ascii=False) + "\n")

print("policy_kb.jsonl 변환 완료")