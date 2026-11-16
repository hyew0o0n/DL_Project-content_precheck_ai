"""LLM 근거 생성 v1  (기획안 4-4 / 출력 JSON v0.2의 evidence·message 채우기)

흐름: finding (분류기·규칙이 만든 것, evidence=[]·message="")
      → rag.search()로 같은 위반 유형의 조항 후보 3개 검색
      → Gemini에게 "후보 중 맞는 조항 고르기 + 안내 문장 쓰기"만 시킴
      → 고른 doc_id의 검색 결과를 그대로 evidence에 복사

사용법
    from llm.explain import explain_findings
    findings = explain_findings(text, findings, ad_detected=False)

조항을 지어내지 못하게 하는 장치 (W5 규칙)
    1. LLM에게는 doc_id만 고르게 하고, evidence의 문서명·조항·링크·상태는 검색 결과에서 복사
    2. LLM이 후보에 없는 doc_id를 내면 버림
    3. 맞는 조항이 없으면 evidence = [] ("근거 없음")

v0.2 3-3 판정 규칙도 여기서 적용
    - 근거가 전부 '예정'·'행정예고'면 위반 → 검토 필요
    - 근거가 없고 LLM 단독 판단(source=llm)이면 → 검토 필요
"""

from __future__ import annotations

import json
import time
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field

from llm.client import generate
from rag.search import search

ROOT = Path(__file__).resolve().parent.parent
KB_PATH = ROOT / "rag" / "policy_kb.jsonl"

K = 3                       # 조항 후보 수 (v0.2 evidence 최대 3개)
KEEP_RULE_MESSAGE = True    # 규칙(source=rule)은 미리 정한 문장 유지 (v0.2 2-4). False면 LLM 문장으로 교체
MAX_PARSE_RETRY = 1         # JSON 파싱 실패 시 재시도 횟수 (W5: 1회)
MAX_RATE_RETRY = 3          # 분당 호출 제한(429) 시 재시도 횟수
BACKOFF_SEC = 5             # 429 첫 대기 시간 → 5, 10, 20초
CALL_GAP_SEC = 1.0          # 여러 finding을 연속 호출할 때 사이 대기 (무료 등급 분당 제한)

NOT_IN_FORCE = {"예정", "행정예고"}
NO_EVIDENCE_MESSAGE = "관련 정책 조항을 찾지 못했어요. 표현이 적절한지 직접 확인해주세요."
FALLBACK_MESSAGE = "{label}(으)로 보이는 표현이 있어요. 아래 근거 조항을 참고해 확인해주세요."
GENERIC_REVIEW_QUESTION ="이 표현이 문제가 될 수 있는지 직접 확인해주세요."


# ───────────── LLM 출력 모양 (client.generate의 schema로 강제) ─────────────
class Explanation(BaseModel):
    used_doc_ids: list[str] = Field(description="후보 조항 중 실제 근거로 쓸 doc_id. 맞는 게 없으면 빈 리스트")
    message: str = Field(description="무엇이, 왜 문제인지 1–2문장 (해요체)")


# ───────────── 정책 본문 불러오기 ─────────────
@lru_cache(maxsize=1)
def _kb_by_id() -> dict:
    """search()는 문서명·조항만 돌려주므로, LLM에게 보여줄 요약·본문은 KB 파일에서 doc_id로 찾음."""
    rows = {}
    with open(KB_PATH, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                r = json.loads(line)
                rows[r["doc_id"]] = r
    return rows


def _risk(verdict: str, conf: float) -> int:
    """v0.2 3-4 위험도 계산식 (predict.py와 같은 식)."""
    return round(60 + 40 * conf) if verdict == "위반" else round(20 + 40 * conf)


# ───────────── 1. 검색 ─────────────
def _query_of(finding: dict) -> str:
    """검색 질문 = 항목 이름 + 걸린 표현."""
    loc = finding.get("location", {})
    snippet = loc.get("text") or loc.get("ocr_text") or ""
    return f"{finding['label']}: {snippet}"[:300]


def retrieve(finding: dict, ad_detected: bool = False, k: int = K) -> list[dict]:
    """광고성 여부와 finding 종류에 따라 정책 검색 범위를 결정한다.

    - 광고성 감지: 광고·홍보 + 전체 정책
    - 비광고 + 광고 규정 finding: purpose 필터 없음
    - 비광고 + 일반 finding: 전체 정책만
    """
    if ad_detected:
        p = "ad"
    elif finding["category"] == "ad_rule":
        p = None
    else:
        p = "none"

    return search(
        _query_of(finding),
        k=k,
        violation_types=[finding["subtype"]],
        purpose=p,
    )

# ───────────── 2. 프롬프트 ─────────────
PROMPT = """너는 광고·SNS 콘텐츠 사전 검수 도우미야. 사람 검수자가 빠르게 판단하도록 근거를 정리해줘.

[검수할 글]
{text}

[탐지된 항목]
- 유형: {label}  (코드: {category}.{subtype})
- 판정: {verdict}
- 문제 구간: "{span_text}"
- 탐지한 단계: {source}  (rule=규칙, classifier=분류 모델)

[근거 후보 조항] (검색 결과, 이 목록 밖의 법령·정책은 절대 쓰지 말 것)
{candidates}

[할 일]
1. used_doc_ids: 위 후보 중 이 항목의 근거로 실제로 맞는 조항의 doc_id만 골라. 0–3개.
   - 후보에 없는 doc_id, 후보에 없는 법령 이름은 만들지 마.
   - 맞는 조항이 하나도 없으면 빈 리스트 [] 로 둬.
2. message: 무엇이, 왜 문제인지 1–2문장, 해요체로.
   - 문제 구간을 짧게 인용하고, 고른 조항 이름을 자연스럽게 언급해.
   - "~될 수 있어요"처럼 가능성으로 말하고, 법적 결론을 단정하지 마.
   - 상태가 '예정'·'행정예고'인 조항은 "시행 예정인 ~에 따르면"처럼 시행 전임을 밝혀.
   - 조항을 하나도 고르지 않았다면 조항을 언급하지 말고 표현 자체의 문제만 말해.
   - 혐오·욕설 표현을 그대로 길게 반복하지 마.
"""


def _format_candidates(cands: list[dict]) -> str:
    if not cands:
        return "(검색된 조항 없음)"
    kb = _kb_by_id()
    lines = []
    for i, c in enumerate(cands, 1):
        row = kb.get(c["doc_id"], {})
        lines.append(
            f"{i}. doc_id={c['doc_id']} | {c['doc']} {c['clause']} | 상태: {c['status']}\n"
            f"   요약: {row.get('summary', '')}\n"
            f"   내용: {row.get('text', '')}"
        )
    return "\n".join(lines)


def build_prompt(text: str, finding: dict, cands: list[dict]) -> str:
    loc = finding.get("location", {})
    return PROMPT.format(
        text=text[:2000],
        label=finding["label"],
        category=finding["category"],
        subtype=finding["subtype"],
        verdict=finding["verdict"],
        span_text=loc.get("text") or loc.get("ocr_text") or "",
        source=finding.get("source", ""),
        candidates=_format_candidates(cands),
    )


# ───────────── 3. LLM 호출 (재시도) ─────────────
def _is_rate_limit(e: Exception) -> bool:
    msg = str(e)
    return getattr(e, "code", None) == 429 or "429" in msg or "RESOURCE_EXHAUSTED" in msg


def call_llm(prompt: str) -> dict | None:
    """schema로 JSON 모양 강제. 파싱 실패는 1회, 429는 backoff로 최대 3회 재시도. 끝내 실패하면 None."""
    parse_fail = rate_fail = 0
    while True:
        try:
            out = generate(prompt, schema=Explanation)
            Explanation(**out)  # 키·타입 확인 (모양이 다르면 ValidationError)
            return out
        except Exception as e:  # noqa: BLE001 - 어떤 오류든 데모가 멈추지 않게
            if _is_rate_limit(e) and rate_fail < MAX_RATE_RETRY:
                wait = BACKOFF_SEC * (2 ** rate_fail)
                print(f"[explain] 호출 제한(429) → {wait}초 후 재시도")
                time.sleep(wait)
                rate_fail += 1
            elif not _is_rate_limit(e) and parse_fail < MAX_PARSE_RETRY:
                print(f"[explain] 응답 오류 → 1회 재시도 ({type(e).__name__}: {str(e)[:80]})")
                parse_fail += 1
            else:
                print(f"[explain] LLM 실패, 검색 결과로 대체 ({type(e).__name__}: {str(e)[:80]})")
                return None


# ───────────── 4. v0.2 판정 규칙 ─────────────
def _apply_verdict_rules(f: dict) -> dict:
    ev = f["evidence"]
    downgrade = False
    if f["verdict"] == "위반" and ev and all(e["status"] in NOT_IN_FORCE for e in ev):
        downgrade = True  # 시행 전 규정으로 위반 판정하지 않음
    if not ev and f.get("source") == "llm":
        downgrade = True  # LLM 단독 + 근거 없음
    if downgrade and f["verdict"] == "위반":
        f["verdict"] = "검토 필요"
        f["risk"] = _risk("검토 필요", f["confidence"])
        f["review_question"] = f.get("review_question") or GENERIC_REVIEW_QUESTION
    return f


# ───────────── 5. 한 항목 / 여러 항목 ─────────────
def explain_finding(text: str, finding: dict, ad_detected: bool = False) -> dict:
    """finding 하나의 evidence·message를 채운 새 dict를 돌려줌 (원본은 그대로)."""
    f = json.loads(json.dumps(finding))  # 깊은 복사
    cands = retrieve(f, ad_detected=ad_detected)
    by_id = {c["doc_id"]: c for c in cands}

    out = call_llm(build_prompt(text, f, cands)) if cands else None

    if out is not None:
        # 후보에 있는 doc_id만, 중복 없이, LLM이 고른 순서대로
        picked = list(dict.fromkeys(d for d in out["used_doc_ids"] if d in by_id))
        dropped = [d for d in out["used_doc_ids"] if d not in by_id]
        f["evidence"] = [by_id[d] for d in picked]
        llm_message = out["message"].strip()
        f["explain_status"] = "ok" if not dropped else f"ok (후보 밖 doc_id 버림: {dropped})"
    elif cands:
        # LLM 실패 → 검색 결과를 그대로 근거로 (지어낸 게 아니라 실제 조항이므로 안전)
        f["evidence"] = cands
        llm_message = ""
        f["explain_status"] = "fallback_search"
    else:
        f["evidence"] = []
        llm_message = ""
        f["explain_status"] = "no_candidates"

    keep = KEEP_RULE_MESSAGE and f.get("source") == "rule" and f.get("message")
    if not keep:
        if llm_message and f["evidence"]:
            f["message"] = llm_message
        elif llm_message:  # 조항은 없지만 표현 자체 설명은 있음
            f["message"] = f"{llm_message} ({NO_EVIDENCE_MESSAGE})"
        elif not f.get("message"):
            f["message"] = (FALLBACK_MESSAGE.format(label=f["label"]) if f["evidence"]
                            else NO_EVIDENCE_MESSAGE)

    return _apply_verdict_rules(f)


def explain_findings(text: str, findings: list[dict], ad_detected: bool = False) -> list[dict]:
    """여러 finding을 차례로 처리. 무료 등급 분당 제한 때문에 호출 사이에 잠깐 쉼."""
    result = []
    for i, f in enumerate(findings):
        if i > 0:
            time.sleep(CALL_GAP_SEC)
        result.append(explain_finding(text, f, ad_detected=ad_detected))
    return result