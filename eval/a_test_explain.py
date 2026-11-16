"""llm/explain.py 동작 확인 (W5)

실행: python -m eval.a_test_explain            # 손으로 만든 분류기 finding 사용 (GPU 안 씀)
      python -m eval.a_test_explain --predict  # 진짜 models/predict.py로 finding 생성 (GPU 사용)

확인하는 것
  - evidence의 doc_id가 전부 RAG 검색 후보 안에 있는지 (= 조항을 지어내지 않았는지)
  - evidence 최대 3개, v0.2 evidence 필드(doc_id·doc·clause·status·url·score) 다 있는지
  - message가 비어 있지 않은지
  - 근거 후보가 없는 유형(historical_symbol)은 evidence = [] 로 나오는지
Gemini 호출 5–6번 (무료 등급이면 1–2분 걸릴 수 있음)
"""

import json
import sys

from llm.explain import explain_findings, retrieve
from rules.ad_patterns import check_ad

EVIDENCE_KEYS = {"doc_id", "doc", "clause", "status", "url", "score"}


def classifier_finding(sent, subtype, label, verdict, conf, hate_target=None, question=None):
    """models/predict.py가 만드는 것과 같은 모양 (W4 a_test_predict 출력 참고)."""
    f = {"id": "f1", "category": "sensitive" if subtype == "political" else "harmful",
         "subtype": subtype, "label": label, "verdict": verdict, "confidence": conf,
         "risk": round((60 if verdict == "위반" else 20) + 40 * conf), "source": "classifier",
         "location": {"modality": "text", "span": [0, len(sent)], "text": sent},
         "evidence": [], "message": "", "review_question": question, "suggestion": None}
    if hate_target:
        f["hate_target"] = hate_target
    return f


def build_cases(use_predict):
    cases = []
    # 1) 광고 규칙 결과 (과대광고 위반 + 표시 누락 검토 필요)
    t1 = "이 크림 하나면 주름 100% 개선! 프로필 링크에서 쿠폰코드 SALE10 입력하세요"
    ad1 = check_ad(t1, "none")
    cases.append(("광고 규칙", t1, ad1["ad_signal"]["detected"], ad1["findings"]))

    # 2) 목적=광고, 식품 다이어트 (시행 예정 조항이 섞여 나오는지)
    t2 = "의사가 추천하는 다이어트 젤리, 먹기만 해도 -5kg!"
    ad2 = check_ad(t2, "ad")
    cases.append(("광고 규칙 (목적=광고)", t2, ad2["ad_signal"]["detected"], ad2["findings"]))

    # 3) 분류기 결과 (혐오·정치)
    t3 = "150억 담보 내놓고 5천억 빌려달라는 전라도 클라스~~~ㅋㅋ"
    t4 = "아직도 박원순 떨어트리기 십자군알바단이설치네요 이명박 치켜세우는글있습니다속지맙시다"
    if use_predict:
        from models.predict import predict
        cases.append(("분류기 (predict)", t3, False, predict(t3)))
        cases.append(("분류기 (predict)", t4, False, predict(t4)))
    else:
        cases.append(("분류기 (손으로 만든 finding)", t3, False,
                      [classifier_finding(t3, "hate", "혐오 표현 (대상: 출신)", "위반", 0.86, "origin")]))
        cases.append(("분류기 (손으로 만든 finding)", t4, False,
                      [classifier_finding(t4, "political", "정치적 표현", "검토 필요", 0.77,
                                          question="정치적으로 해석될 수 있는 표현이 있습니다.")]))

    # 4) KB에 조항이 없는 유형 → evidence [] 이어야 함
    f5 = classifier_finding("욱일기 문양 배경", "historical_symbol", "역사·외교 민감 상징", "검토 필요", 0.7)
    f5["category"], f5["source"] = "sensitive", "vlm"
    cases.append(("근거 없는 유형", "욱일기 문양 배경", False, [f5]))
    return cases


def check(text, ad_detected, before, after):
    errors = []
    for b, a in zip(before, after):
        allowed = {c["doc_id"] for c in retrieve(b, ad_detected=ad_detected)}
        ids = [e["doc_id"] for e in a["evidence"]]
        if not set(ids) <= allowed:
            errors.append(f"{a['id']}: 후보 밖 doc_id {set(ids) - allowed}")
        if len(ids) > 3:
            errors.append(f"{a['id']}: evidence {len(ids)}개 (최대 3)")
        for e in a["evidence"]:
            if set(e) != EVIDENCE_KEYS:
                errors.append(f"{a['id']}: evidence 필드 {set(e) ^ EVIDENCE_KEYS}")
        if not a["message"].strip():
            errors.append(f"{a['id']}: message 비어 있음")
        if a["subtype"] == "historical_symbol" and a["evidence"]:
            errors.append(f"{a['id']}: KB에 없는 유형인데 evidence가 있음")
    return errors


def main():
    use_predict = "--predict" in sys.argv
    total_err, n = [], 0
    for name, text, ad_detected, findings in build_cases(use_predict):
        print(f"\n=== {name} | ad_detected={ad_detected}\n글: {text}")
        if not findings:
            print("  (finding 없음)")
            continue
        after = explain_findings(text, findings, ad_detected=ad_detected)
        for b, a in zip(findings, after):
            n += 1
            changed = f"  ← 판정 변경 ({b['verdict']}→{a['verdict']})" if a["verdict"] != b["verdict"] else ""
            print(f"\n  [{a['id']}] {a['label']} | {a['verdict']} | risk {a['risk']} | {a['explain_status']}{changed}")
            print(f"  구간: {a['location'].get('text')}")
            print(f"  message: {a['message']}")
            for e in a["evidence"]:
                print(f"    - {e['doc_id']} ({e['status']}, {e['score']}) {e['doc']} {e['clause']}")
            if not a["evidence"]:
                print("    - 근거 없음")
        errs = check(text, ad_detected, findings, after)
        for e in errs:
            print(f"  ✗ {e}")
        total_err += errs

    print("\n예시 1번 첫 finding 전체 (v0.2 모양)")
    t1 = "이 크림 하나면 주름 100% 개선! 프로필 링크에서 쿠폰코드 SALE10 입력하세요"
    ad1 = check_ad(t1)
    print(json.dumps(
        explain_findings(
            t1,
            ad1["findings"][:1],
            ad_detected=ad1["ad_signal"]["detected"],
        )[0],
        ensure_ascii=False,
        indent=2,
    ))

    print(f"\n{'OK' if not total_err else 'CHECK'}: finding {n}개, 문제 {len(total_err)}건")


if __name__ == "__main__":
    main()