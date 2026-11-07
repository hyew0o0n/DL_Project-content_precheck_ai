"""텍스트 MVP 통합 파이프라인.

흐름:
PII 규칙 → 분류기 → 광고 규칙/광고성 감지 → RAG + LLM 설명 → 최종 JSON (v0.3)

v0.3 = v0.2 + evidence[].excerpt, evidence[].applies_to (rag/search.py가 채움)
"""

import time                      # [추가] meta.elapsed_ms
import uuid                      # [추가] input.id
from datetime import date        # [추가] meta.policy_kb_version
from pathlib import Path         # [추가]

from rules.pii import detect_pii
from rules.ad_patterns import check_ad
from models.predict import predict
from llm.explain import explain_findings


SCHEMA_VERSION = "0.3"                                          # [추가]
KB_PATH = Path(__file__).resolve().parent / "rag" / "policy_kb.jsonl"   # [추가]

VERDICT_ORDER = {
    "통과": 0,
    "검토 필요": 1,
    "위반": 2,
}


def _risk(verdict: str, confidence: float) -> int:
    """v0.2 3-4 위험도 계산식."""
    if verdict == "위반":
        return round(60 + 40 * confidence)
    if verdict == "검토 필요":
        return round(20 + 40 * confidence)
    return 0


def _normalize_findings(findings: list[dict]) -> list[dict]:
    """서로 다른 모듈의 finding을 v0.2 공통 모양으로 맞춘다."""
    normalized = []

    for i, finding in enumerate(findings, 1):
        f = dict(finding)

        f["id"] = f"f{i}"
        f.setdefault("evidence", [])
        f.setdefault("message", "")
        f.setdefault("review_question", None)
        f.setdefault("suggestion", None)

        if "risk" not in f:
            f["risk"] = _risk(
                f.get("verdict", "통과"),
                float(f.get("confidence", 0.0)),
            )

        normalized.append(f)

    return normalized


def _overall_verdict(findings: list[dict]) -> str:
    """findings 중 가장 심한 판정을 전체 verdict로 사용."""
    if not findings:
        return "통과"

    return max(
        (f.get("verdict", "통과") for f in findings),
        key=lambda verdict: VERDICT_ORDER.get(verdict, 0),
    )


# [추가] 한 줄 요약 — 예: "과대·과장 광고 1건, 협찬·대가성 표시 누락 1건"
def _summary(findings: list[dict]) -> str:
    if not findings:
        return "발견된 문제가 없어요"

    counts = {}
    for f in findings:
        label = f.get("label", f.get("subtype", "기타"))
        counts[label] = counts.get(label, 0) + 1

    return ", ".join(f"{label} {n}건" for label, n in counts.items())


# [추가] 정책 KB(JSONL)를 마지막으로 만든 날짜
def _policy_kb_version() -> str:
    try:
        return date.fromtimestamp(KB_PATH.stat().st_mtime).isoformat()
    except OSError:
        return ""


def run_pipeline(text: str, purpose: str = "none", input_id: str | None = None) -> dict:   # [수정] input_id 인자 추가 (선택)
    """글 하나를 검사하고 텍스트 MVP 최종 JSON을 반환한다."""
    if not isinstance(text, str):
        raise TypeError("text는 문자열이어야 합니다.")

    t0 = time.time()   # [추가]

    # 1. 광고성 감지를 먼저 수행한다.
    ad = check_ad(text, purpose)

    # 2. 규칙 + 분류기 + 광고 규칙 finding을 합친다.
    findings = (
        detect_pii(text)
        + predict(text)
        + ad["findings"]
    )

    # 3. id·risk 등 공통 필드를 맞춘다.
    findings = _normalize_findings(findings)

    # 4. 광고성 여부를 반영해 RAG 근거 검색 + LLM 설명을 붙인다.
    findings = explain_findings(
        text,
        findings,
        ad_detected=ad["ad_signal"]["detected"],
    )

    # 5. 최종 출력에는 내부 디버그용 rule_id를 제거한다.
    for finding in findings:
        finding.pop("rule_id", None)

    # 6. LLM 단계에서 판정이 변경될 수 있으므로 마지막에 전체 판정을 계산한다.
    verdict = _overall_verdict(findings)
    risk_score = max(
        (int(f.get("risk", 0)) for f in findings),
        default=0,
    )

    return {
        "schema_version": SCHEMA_VERSION,                         # [추가]
        "input": {                                                # [추가]
            "id": input_id or f"text_{uuid.uuid4().hex[:8]}",
            "media_type": "text",
            "purpose": purpose,
        },
        "verdict": verdict,
        "risk_score": risk_score,
        "ad_signal": ad["ad_signal"],
        "summary": _summary(findings),                            # [추가]
        "findings": findings,
        "meta": {                                                 # [추가]
            "policy_kb_version": _policy_kb_version(),
            "elapsed_ms": round((time.time() - t0) * 1000),
        },
    }


# app.py 등에서 analyze()라는 이름을 써도 같은 함수가 동작하도록 제공
analyze = run_pipeline
run = run_pipeline   # [추가] app.py는 run → analyze 순서로 찾음