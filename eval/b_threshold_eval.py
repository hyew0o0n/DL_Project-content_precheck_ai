import os
os.environ.setdefault("HF_HOME", "/nfs/team/hf_cache")

import csv
from pathlib import Path

import numpy as np
import torch
from datasets import load_dataset
from sklearn.metrics import f1_score
from transformers import AutoModelForSequenceClassification, AutoTokenizer

ROOT = Path(__file__).resolve().parent
CKPT = Path.home() / "project" / "checkpoints" / "v3" / "final"

LABEL_NAMES = [
    "origin", "physical", "politics", "profanity",
    "age", "gender", "race", "religion", "not_hate",
]

# 정치(2), not_hate(8)는 위반 threshold 계산에서 제외
HARMFUL_IDX = [0, 1, 3, 4, 5, 6, 7]
POLITICS_IDX = 2

BATCH_SIZE = 64
MAX_LENGTH = 64

device = "cuda" if torch.cuda.is_available() else "cpu"

print("device =", device)
print("checkpoint =", CKPT)
print("validation split만 불러옵니다. test split은 사용하지 않습니다.")

# validation만 직접 로드: 공식 test를 건드리지 않음
ds = load_dataset(
    "jeanlee/kmhas_korean_hate_speech",
    split="validation",
)

texts = [str(x).strip() for x in ds["text"]]

y_true = np.zeros((len(ds), 9), dtype=np.int8)
for row, labels in enumerate(ds["label"]):
    for label in labels:
        y_true[row, int(label)] = 1

print("validation =", len(texts))

tok = AutoTokenizer.from_pretrained(CKPT)
model = AutoModelForSequenceClassification.from_pretrained(CKPT)
model = model.to(device).eval()

all_probs = []

with torch.no_grad():
    for start in range(0, len(texts), BATCH_SIZE):
        batch = texts[start:start + BATCH_SIZE]

        enc = tok(
            batch,
            truncation=True,
            max_length=MAX_LENGTH,
            padding=True,
            return_tensors="pt",
        ).to(device)

        logits = model(**enc).logits
        probs = torch.sigmoid(logits).cpu().numpy()
        all_probs.append(probs)

        done = min(start + BATCH_SIZE, len(texts))
        if done % 1024 < BATCH_SIZE or done == len(texts):
            print(f"inference: {done}/{len(texts)}")

y_prob = np.concatenate(all_probs, axis=0)

assert y_prob.shape == y_true.shape == (len(texts), 9)

results_dir = Path.home() / "project" / "results"
results_dir.mkdir(exist_ok=True)

np.savez_compressed(
    results_dir / "b_threshold_probs.npz",
    y_true=y_true,
    y_prob=y_prob,
)

print("saved: results/b_threshold_probs.npz")


def safe_div(a, b):
    return float(a / b) if b else 0.0


rows = []

# 0.1 단위로 두 경계값 탐색
for review_t in np.arange(0.1, 0.9, 0.1):
    for violation_t in np.arange(review_t + 0.1, 1.0, 0.1):

        review_t = round(float(review_t), 1)
        violation_t = round(float(violation_t), 1)

        # -----------------------------
        # 1) 혐오/욕설 7개
        # -----------------------------
        yh = y_true[:, HARMFUL_IDX]
        ph = y_prob[:, HARMFUL_IDX]

        violation_mask = ph >= violation_t
        review_mask = (ph >= review_t) & (ph < violation_t)
        flagged_mask = ph >= review_t
        pass_mask = ph < review_t

        violation_tp = int(((yh == 1) & violation_mask).sum())
        violation_pred = int(violation_mask.sum())
        harmful_positive = int((yh == 1).sum())

        violation_precision = safe_div(
            violation_tp,
            violation_pred,
        )

        violation_recall = safe_div(
            violation_tp,
            harmful_positive,
        )

        review_rate = safe_div(
            int(review_mask.sum()),
            review_mask.size,
        )

        positive_review_rate = safe_div(
            int(((yh == 1) & review_mask).sum()),
            harmful_positive,
        )

        miss_rate = safe_div(
            int(((yh == 1) & pass_mask).sum()),
            harmful_positive,
        )

        harmful_pred = flagged_mask.astype(int)
        harmful_macro_f1 = f1_score(
            yh,
            harmful_pred,
            average="macro",
            zero_division=0,
        )

        # -----------------------------
        # 2) 정치
        # 정치 표현은 위반으로 승격하지 않고
        # review_t 이상이면 검토 필요로 본다.
        # -----------------------------
        yp = y_true[:, POLITICS_IDX]
        pp = y_prob[:, POLITICS_IDX]

        politics_pred = pp >= review_t

        politics_tp = int(((yp == 1) & politics_pred).sum())
        politics_pred_n = int(politics_pred.sum())
        politics_positive = int((yp == 1).sum())

        politics_precision = safe_div(
            politics_tp,
            politics_pred_n,
        )

        politics_recall = safe_div(
            politics_tp,
            politics_positive,
        )

        rows.append({
            "review_threshold": review_t,
            "violation_threshold": violation_t,
            "violation_precision": violation_precision,
            "violation_recall": violation_recall,
            "review_rate": review_rate,
            "positive_review_rate": positive_review_rate,
            "miss_rate": miss_rate,
            "harmful_macro_f1_flagged": harmful_macro_f1,
            "politics_precision": politics_precision,
            "politics_recall": politics_recall,
        })


csv_path = results_dir / "b_threshold_grid.csv"

with csv_path.open("w", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(
        f,
        fieldnames=list(rows[0].keys()),
    )
    writer.writeheader()
    writer.writerows(rows)

print("saved:", csv_path)


# 대표 조합 출력
representative = {
    (0.2, 0.6),
    (0.2, 0.7),
    (0.2, 0.8),
    (0.3, 0.6),
    (0.3, 0.7),
    (0.3, 0.8),
    (0.4, 0.6),
    (0.4, 0.7),
    (0.4, 0.8),
    (0.5, 0.7),
    (0.5, 0.8),
    (0.5, 0.9),
}

print()
print("===== 대표 threshold 조합 =====")
print(
    "review  violation | "
    "위반정밀도 위반recall 검토비율 miss비율 "
    "harmful_macroF1 | 정치precision 정치recall"
)

for r in rows:
    key = (
        r["review_threshold"],
        r["violation_threshold"],
    )

    if key not in representative:
        continue

    print(
        f"{r['review_threshold']:.1f}     "
        f"{r['violation_threshold']:.1f}       | "
        f"{r['violation_precision']:.4f}    "
        f"{r['violation_recall']:.4f}    "
        f"{r['review_rate']:.4f}   "
        f"{r['miss_rate']:.4f}   "
        f"{r['harmful_macro_f1_flagged']:.4f}       | "
        f"{r['politics_precision']:.4f}        "
        f"{r['politics_recall']:.4f}"
    )

print()
print("OK: validation threshold grid 계산 완료")
