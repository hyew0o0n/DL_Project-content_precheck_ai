
"""개인정보 정규식 → 출력 JSON v0.2 findings"""
import re

# (subtype, 화면 이름, 정규식, 판정, confidence)
PII_RULES = [
    ("rrn",     "주민등록번호", r"(?<!\d)\d{6}-?[1-4]\d{6}(?!\d)", "위반", 0.99),
    ("phone",   "전화번호", r"(?<!\d)01[016789][-. ]?\d{3,4}[-. ]?\d{4}(?!\d)", "위반", 0.99),
    ("email",   "이메일", r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+", "위반", 0.99),
    ("account", "계좌번호", r"(?<!\d)\d{2,6}-\d{2,6}-\d{2,6}(?:-\d{1,6})?(?!\d)", "검토 필요", 0.7),
]


def detect_pii(text):
    findings, taken = [], []
    for subtype, label, pattern, verdict, conf in PII_RULES:
        for m in re.finditer(pattern, text):
            s, e = m.span()
            if any(s < te and ts < e for ts, te in taken):   # 앞 규칙이 잡은 자리는 건너뜀
                continue
            if subtype == "account" and not 10 <= len(re.sub(r"\D", "", m.group())) <= 14:
                continue                                       # 계좌는 숫자 10~14자리만
            taken.append((s, e))
            findings.append({
                "category": "privacy",
                "subtype": subtype,
                "label": f"개인정보 ({label})",
                "verdict": verdict,
                "confidence": conf,
                "source": "rule",
                "location": {"modality": "text", "span": [s, e], "text": m.group()},
                "evidence": [],            # RAG 단계가 PIPA-15-1을 채움
                "review_question": "실제 계좌번호인가요? 그렇다면 가려주세요." if verdict == "검토 필요" else None,
            })
    return sorted(findings, key=lambda f: f["location"]["span"][0])
