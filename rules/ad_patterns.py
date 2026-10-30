"""광고성 감지 + 과대광고 패턴 ad_v1  (기획안 5-1, 5-2 / 출력 JSON v0.2)

패턴은 rules/ad_patterns.yaml에만 있음 → 패턴을 고칠 때 이 파일은 건드리지 않음.

사용법
    from rules.ad_patterns import check_ad
    out = check_ad("이 크림 하나면 주름 100% 개선! 프로필 링크에서 쿠폰코드 SALE10", purpose="none")
    out["ad_signal"]   # v0.2 2-3 ad_signal (그대로 최상위에 넣으면 됨)
    out["findings"]    # v0.2 2-4 findings (exaggeration, missing_disclosure)

- findings의 id는 "f1, f2…"로 임시로 붙임 → pipeline.py에서 합칠 때 다시 번호 매김
- evidence는 비워둠([]) → llm/explain.py(RAG) 단계에서 채움
- message·review_question은 YAML의 고정 문장 (규칙 단계는 LLM을 쓰지 않음)
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import yaml

PATTERN_PATH = Path(__file__).with_name("ad_patterns.yaml")
EXCLUDE_WINDOW = 10  # exclude 정규식을 찾는 범위 (걸린 표현 앞뒤 글자 수)
DISCLOSURE_CONFIDENCE_AD = 0.9  # purpose=ad인데 표시가 없을 때 (v0.2 예시 2와 같은 값)


# ───────────── 패턴 불러오기 ─────────────
@lru_cache(maxsize=1)
def load_patterns(path: str | None = None) -> dict:
    """YAML을 읽어 정규식을 미리 컴파일해 둠 (처음 한 번만)."""
    with open(path or PATTERN_PATH, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    def comp(p):
        return re.compile(p, re.IGNORECASE | re.MULTILINE)

    for item in cfg["disclosure"]:
        item["re"] = comp(item["regex"])
    for item in cfg["ad_signal"]["patterns"]:
        item["re"] = comp(item["regex"])
    for item in cfg["exaggeration"]:
        item["re"] = comp(item["regex"])
        item["exclude_re"] = comp(item["exclude"]) if item.get("exclude") else None
    return cfg


def risk_of(verdict: str, confidence: float) -> int:
    """v0.2 3-4 위험도 계산식 (models/predict.py와 같은 식)."""
    if verdict == "위반":
        return round(60 + 40 * confidence)
    return round(20 + 40 * confidence)


def _first_sentence_hint(hint: str) -> str:
    """'최초 주장 (실증 자료 필요)' → '최초 주장'  (안내 문장에는 괄호 앞부분만)."""
    return hint.split(" (")[0]


# ───────────── 1. 광고 표시 문구 ─────────────
def find_disclosure(text: str) -> list[dict]:
    """'#광고', '협찬받아' 같은 표시 문구 위치 목록."""
    cfg = load_patterns()
    hits = []
    for p in cfg["disclosure"]:
        for m in p["re"].finditer(text):
            hits.append({"id": p["id"], "span": [m.start(), m.end()], "text": m.group()})
    return hits


# ───────────── 2. 광고성 신호 ─────────────
def find_ad_signals(text: str) -> tuple[float, list[dict]]:
    """광고성 점수(0–1)와 걸린 신호 목록. 같은 패턴은 여러 번 나와도 점수에 1번만 반영."""
    cfg = load_patterns()
    hits, used = [], set()
    remain = 1.0
    for p in cfg["ad_signal"]["patterns"]:
        for m in p["re"].finditer(text):
            hits.append({"id": p["id"], "weight": p["weight"],
                         "span": [m.start(), m.end()], "text": m.group()})
            if p["id"] not in used:
                used.add(p["id"])
                remain *= 1 - p["weight"]
    hits.sort(key=lambda h: h["span"][0])
    return round(1 - remain, 4), hits


# ───────────── 3. 과대광고 ─────────────
def find_exaggerations(text: str) -> list[dict]:
    """과대광고 표현 목록. 겹치는 구간은 더 심한 것(위반 > 검토 필요, 그다음 confidence) 하나만 남김."""
    cfg = load_patterns()
    raw = []
    for p in cfg["exaggeration"]:
        for m in p["re"].finditer(text):
            s, e = m.start(), m.end()
            if p["exclude_re"]:
                window = text[max(0, s - EXCLUDE_WINDOW): e + EXCLUDE_WINDOW]
                if p["exclude_re"].search(window):
                    continue
            raw.append({"id": p["id"], "span": [s, e], "text": m.group(),
                        "verdict": p["verdict"], "confidence": p["confidence"],
                        "hint": p["label_hint"]})

    # 겹침 제거: 심한 것부터 넣고, 이미 넣은 구간과 겹치면 버림
    severity = lambda h: (h["verdict"] == "위반", h["confidence"], h["span"][1] - h["span"][0])
    kept = []
    for h in sorted(raw, key=severity, reverse=True):
        if all(h["span"][1] <= k["span"][0] or h["span"][0] >= k["span"][1] for k in kept):
            kept.append(h)
    return sorted(kept, key=lambda h: h["span"][0])


# ───────────── 합치기: v0.2 모양으로 ─────────────
def check_ad(text: str, purpose: str = "none") -> dict:
    """광고 관련 규칙 검사 전체. 반환: {"ad_signal": {...}, "findings": [...]}"""
    cfg = load_patterns()
    msgs = cfg["messages"]

    disclosures = find_disclosure(text)
    score, signals = find_ad_signals(text)
    threshold = cfg["ad_signal"]["threshold"]

    # ad_signal (v0.2 2-3)
    if purpose == "ad":
        ad_signal = {"detected": True, "by": "purpose", "score": 1.0}
    elif score >= threshold:
        ad_signal = {"detected": True, "by": "rule", "score": score}
    else:
        ad_signal = {"detected": False, "by": "none", "score": 0.0}
    ad_signal["disclosure_found"] = bool(disclosures)

    findings = []

    # (1) 과대광고 — 광고성 여부와 무관하게 항상
    for h in find_exaggerations(text):
        hint = _first_sentence_hint(h["hint"])
        findings.append({
            "category": "ad_rule",
            "subtype": "exaggeration",
            "label": "과대·과장 광고",
            "verdict": h["verdict"],
            "confidence": h["confidence"],
            "risk": risk_of(h["verdict"], h["confidence"]),
            "source": "rule",
            "location": {"modality": "text", "span": h["span"], "text": h["text"]},
            "evidence": [],
            "message": msgs["exaggeration"][h["verdict"]].format(text=h["text"], hint=hint),
            "review_question": msgs["exaggeration_question"] if h["verdict"] == "검토 필요" else None,
            "suggestion": None,
            "rule_id": h["id"],  # 디버그용 (어느 패턴이 걸렸는지). 최종 출력 전에 빼도 됨
        })

    # (2) 표시 누락 — 광고성이고 표시 문구가 없을 때만
    if ad_signal["detected"] and not ad_signal["disclosure_found"]:
        if purpose == "ad":
            verdict, conf = "위반", DISCLOSURE_CONFIDENCE_AD
            location = {"modality": "text", "span": [0, len(text)], "text": text}
            message, question = msgs["missing_disclosure"]["ad"], None
        else:
            verdict, conf = "검토 필요", score
            first = signals[0]  # 가장 앞에 나온 홍보 표현을 위치로
            location = {"modality": "text", "span": first["span"], "text": first["text"]}
            message = msgs["missing_disclosure"]["none"].format(text=first["text"])
            question = msgs["missing_disclosure_question"]
        findings.append({
            "category": "ad_rule",
            "subtype": "missing_disclosure",
            "label": "협찬·대가성 표시 누락",
            "verdict": verdict,
            "confidence": round(conf, 4),
            "risk": risk_of(verdict, conf),
            "source": "rule",
            "location": location,
            "evidence": [],
            "message": message,
            "review_question": question,
            "suggestion": None,
            "rule_id": ",".join(sorted({s["id"] for s in signals})) or "purpose",
        })

    for i, f in enumerate(findings, 1):
        f["id"] = f"f{i}"
    findings = [{"id": f.pop("id"), **f} for f in findings]  # id를 맨 앞으로

    return {"ad_signal": ad_signal, "findings": findings,
            "debug": {"signals": signals, "disclosures": disclosures}}