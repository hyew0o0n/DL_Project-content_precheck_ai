"""predict()가 출력 JSON v0.2 findings 모양으로 나오는지 확인 (validation 10문장)

실행: cd ~/project && python -m eval.a_test_predict
"""
import json

from data.kmhas import LABEL_NAMES, load_kmhas
from models.predict import predict, split_sentences

REQUIRED = {"id": str, "category": str, "subtype": str, "label": str, "verdict": str,
            "confidence": float, "risk": int, "source": str, "location": dict,
            "evidence": list, "message": str}
NULLABLE = ("review_question", "suggestion")


def check(f, text):
    for k, t in REQUIRED.items():
        assert k in f and isinstance(f[k], t), f"{k} 누락 또는 타입 오류: {f.get(k)!r}"
    for k in NULLABLE:
        assert k in f, f"{k} 누락"
    assert f["source"] == "classifier"
    assert f["verdict"] in ("위반", "검토 필요")
    assert 0 <= f["confidence"] <= 1 and 0 <= f["risk"] <= 100
    loc = f["location"]
    s, e = loc["span"]
    assert loc["modality"] == "text" and text[s:e] == loc["text"], "span과 text 불일치"
    if f["subtype"] == "hate":
        assert f.get("hate_target"), "hate인데 hate_target 없음"
    else:
        assert "hate_target" not in f
    if f["verdict"] == "검토 필요":
        assert f["review_question"], "검토 필요인데 review_question 없음"
    assert f["evidence"] == [] and f["message"] == ""


_, val, _ = load_kmhas()
is_clean = val["labels"].apply(lambda v: v[-1] == 1)      # 마지막 = not_hate
hate = val[~is_clean].sample(7, random_state=42)
clean = val[is_clean].sample(3, random_state=42)

n_findings = 0
for i, row in enumerate(list(hate.itertuples()) + list(clean.itertuples())):
    gold = [LABEL_NAMES[j] for j, v in enumerate(row.labels) if v]
    findings = predict(row.text)
    for f in findings:
        check(f, row.text)
    n_findings += len(findings)
    print(f"\n[{i}] 정답 {gold} | {row.text}")
    print(json.dumps(findings, ensure_ascii=False, indent=2))

# 여러 문장이 섞인 글: 문장별로 span이 나뉘는지
multi = hate.iloc[0]["text"] + " 오늘 날씨 좋네요. " + hate.iloc[1]["text"]
print("\n[여러 문장]", multi)
print("문장 나누기:", [multi[s:e] for s, e in split_sentences(multi)])
for f in predict(multi):
    check(f, multi)
    print(f["id"], f["subtype"], f.get("hate_target"), f["location"]["span"], f["location"]["text"])

print(f"\nOK: 10문장 + 여러 문장 1개, findings {n_findings}개 모두 v0.2 모양")