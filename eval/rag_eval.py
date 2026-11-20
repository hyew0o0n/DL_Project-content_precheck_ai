"""RAG 검색 정답셋 평가 (Recall@k)

정답셋: eval/data/rag/rag_gold.jsonl  (질문 1개 = 정답 doc_id 목록, 그중 하나라도 Top-k에 있으면 Hit)
    - Q01–Q20: W5 b_rag_eval.md 질문 (Q17·Q18은 W8 KB 분리 후 새 doc_id로 정답 교체)
    - Q21–Q25: W8 로고·캐릭터 3개 + 초상 2개 추가

실행 (서버, KB를 26개로 재빌드한 뒤)
    python -m eval.rag_eval            # filter OFF, k=3
    python -m eval.rag_eval --k 5
결과: results/rag_eval.md
"""
import argparse
import json
from pathlib import Path

from rag.search import search

ROOT = Path(__file__).resolve().parent.parent
GOLD = ROOT / "eval" / "data" / "rag" / "rag_gold.jsonl"
OUT = ROOT / "results" / "rag_eval.md"


def main(k: int = 3):
    rows = [json.loads(l) for l in GOLD.read_text(encoding="utf-8").splitlines() if l.strip()]
    lines, hits = [], 0
    for r in rows:
        top = [c["doc_id"] for c in search(r["question"], k=k)]   # filter OFF (W5와 같은 조건)
        hit = any(g in top for g in r["gold"])
        hits += hit
        lines.append(f'| {r["id"]} | {r["question"]} | {", ".join(r["gold"])} | {"<br>".join(top)} | {"O" if hit else "X"} |')
        print(f'{r["id"]} {"O" if hit else "X"}  top={top}  gold={r["gold"]}')
    recall = hits / len(rows)
    md = [f"# RAG 검색 평가 (Recall@{k}, filter OFF)", "",
          f"- 질문: {len(rows)}개 (W5 20개 + W8 권리 5개)",
          f"- Hit: **{hits}/{len(rows)}**  /  Recall@{k}: **{recall:.4f}**", "",
          f"| # | 질문 | 정답 doc_id (하나라도 맞으면 Hit) | Top {k} | Hit |", "|---|---|---|---|:---:|", *lines]
    OUT.write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"\nRecall@{k} = {hits}/{len(rows)} = {recall:.4f} → {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=3)
    main(ap.parse_args().k)
