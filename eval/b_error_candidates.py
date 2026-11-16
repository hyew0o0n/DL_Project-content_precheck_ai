import os
os.environ.setdefault("HF_HOME", "/nfs/team/hf_cache")

import csv
from pathlib import Path

import numpy as np
from datasets import load_dataset

ROOT = Path.home() / "project"
RESULTS = ROOT / "results"
PROB_PATH = RESULTS / "b_threshold_probs.npz"

LABEL_NAMES = [
    "origin", "physical", "politics", "profanity",
    "age", "gender", "race", "religion", "not_hate",
]
LABEL_KO = [
    "출신", "외모", "정치", "욕설",
    "연령", "성별", "인종", "종교", "해당없음",
]

REVIEW_THRESHOLD = 0.4
ACTIONABLE_IDX = list(range(8))  # not_hate 제외

print("validation만 사용합니다. official test는 사용하지 않습니다.")

saved = np.load(PROB_PATH)
y_true = saved["y_true"]
y_prob = saved["y_prob"]

ds = load_dataset(
    "jeanlee/kmhas_korean_hate_speech",
    split="validation",
)
texts = [str(x).strip() for x in ds["text"]]

assert len(texts) == len(y_true) == len(y_prob)

errors = []

for row_idx, text in enumerate(texts):
    true_labels = [
        LABEL_NAMES[i]
        for i in range(9)
        if y_true[row_idx, i] == 1
    ]

    pred_labels = [
        LABEL_NAMES[i]
        for i in ACTIONABLE_IDX
        if y_prob[row_idx, i] >= REVIEW_THRESHOLD
    ]

    for i in ACTIONABLE_IDX:
        y = int(y_true[row_idx, i])
        p = float(y_prob[row_idx, i])

        if y == 1 and p < REVIEW_THRESHOLD:
            errors.append({
                "row": row_idx,
                "error_type": "미탐(FN)",
                "label": LABEL_NAMES[i],
                "label_ko": LABEL_KO[i],
                "prob": p,
                "true_labels": ", ".join(true_labels),
                "pred_labels": ", ".join(pred_labels) if pred_labels else "-",
                "text": text,
            })

        elif y == 0 and p >= REVIEW_THRESHOLD:
            errors.append({
                "row": row_idx,
                "error_type": "오탐(FP)",
                "label": LABEL_NAMES[i],
                "label_ko": LABEL_KO[i],
                "prob": p,
                "true_labels": ", ".join(true_labels),
                "pred_labels": ", ".join(pred_labels) if pred_labels else "-",
                "text": text,
            })


def balanced_pick(candidates, error_type, n, used_texts):
    pool = [x for x in candidates if x["error_type"] == error_type]

    buckets = {i: [] for i in ACTIONABLE_IDX}

    for x in pool:
        idx = LABEL_NAMES.index(x["label"])
        buckets[idx].append(x)

    # 가장 뚜렷한 오류부터:
    # FN은 확률이 낮은 순, FP는 확률이 높은 순
    for idx in ACTIONABLE_IDX:
        buckets[idx].sort(
            key=lambda x: x["prob"],
            reverse=(error_type == "오탐(FP)"),
        )

    selected = []

    # 라벨별 round-robin
    while len(selected) < n:
        added = False

        for idx in ACTIONABLE_IDX:
            while buckets[idx]:
                x = buckets[idx].pop(0)

                if x["text"] in used_texts:
                    continue

                selected.append(x)
                used_texts.add(x["text"])
                added = True
                break

            if len(selected) >= n:
                break

        if not added:
            break

    return selected


used_texts = set()

fn_selected = balanced_pick(
    errors,
    "미탐(FN)",
    15,
    used_texts,
)

fp_selected = balanced_pick(
    errors,
    "오탐(FP)",
    15,
    used_texts,
)

selected = fn_selected + fp_selected

assert len(selected) == 30, f"30개를 못 뽑음: {len(selected)}개"

csv_path = RESULTS / "b_error_candidates.csv"

with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
    writer = csv.DictWriter(
        f,
        fieldnames=[
            "no", "error_type", "label", "label_ko", "prob",
            "true_labels", "pred_labels", "text",
        ],
    )
    writer.writeheader()

    for no, x in enumerate(selected, 1):
        writer.writerow({
            "no": no,
            "error_type": x["error_type"],
            "label": x["label"],
            "label_ko": x["label_ko"],
            "prob": f"{x['prob']:.4f}",
            "true_labels": x["true_labels"],
            "pred_labels": x["pred_labels"],
            "text": x["text"],
        })

md_path = RESULTS / "b_error_candidates.md"

lines = [
    "# W6 오류 분석 후보 30개",
    "",
    "## 기준",
    "",
    "- 모델: v3 KcELECTRA + class weight",
    "- 데이터: K-MHaS validation",
    "- review threshold: 0.4",
    "- 미탐(FN): 실제 라벨이 있지만 probability < 0.4",
    "- 오탐(FP): 실제 라벨이 없지만 probability >= 0.4",
    "- not_hate는 finding 생성 대상이 아니므로 제외",
    "- 미탐 15개 + 오탐 15개, 중복 문장 제외",
    "",
    "※ 이 파일은 오류 사례 후보를 자동 추출한 것이며,",
    "오류 원인(반어·은어 / 변형 표기 / 라벨 애매 / 문맥 부족 등)은",
    "문장을 직접 확인한 뒤 `b_error_analysis.md`에서 정리한다.",
    "",
]

for no, x in enumerate(selected, 1):
    lines += [
        f"### {no}. {x['error_type']} · {x['label']}({x['label_ko']}) · p={x['prob']:.4f}",
        "",
        f"- 실제 라벨: `{x['true_labels']}`",
        f"- 모델 탐지(>=0.4): `{x['pred_labels']}`",
        f"- 문장: {x['text']}",
        "",
    ]

md_path.write_text("\n".join(lines), encoding="utf-8")

print("전체 오류 후보:", len(errors))
print("미탐 선택:", len(fn_selected))
print("오탐 선택:", len(fp_selected))
print("saved:", csv_path)
print("saved:", md_path)

print("\n===== 선택된 30개 =====")
for no, x in enumerate(selected, 1):
    print(
        f"{no:02d}. {x['error_type']} | "
        f"{x['label']}({x['label_ko']}) | "
        f"p={x['prob']:.4f}"
    )
    print("    실제:", x["true_labels"])
    print("    탐지:", x["pred_labels"])
    print("    문장:", x["text"])

print("\nOK: 오류 분석 후보 30개 추출 완료")
