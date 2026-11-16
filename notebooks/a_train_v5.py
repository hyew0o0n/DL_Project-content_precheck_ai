"""분류기 업그레이드 학습 (v5~) — b_train_v3.ipynb를 .py로 옮기고 3가지를 바꿈

v3에서 바꾼 점
  1. class weight를 약하게: 가중치를 그대로(race 329배) 쓰지 않고 제곱근(race 약 18배)으로
     → v3은 race를 살렸지만(0.00→0.34) 다른 라벨 precision이 다 떨어짐. 그 중간을 노림
  2. epoch 3 → 5, 가장 좋은 epoch 자동 선택 (val macro F1 기준, 원래 설정 그대로)
  3. 학습 끝나면 라벨별 임계값 튜닝까지 자동 (a_tune_threshold.py 함수 재사용)
  + (선택) race 문장만 train에서 N배 복제 (--race-oversample)

실행 (서버, ~/project에서 / screen 안에서 권장 — models/README.md 참고):
    python notebooks/a_train_v5.py --version v5 2>&1 | tee -a results/a_train_v5.log

여러 실험 예시 (한 번에 하나씩, 3 epoch 약 6분 → 5 epoch 약 10분):
    python notebooks/a_train_v5.py --version v5                         # 약한 가중치(sqrt) + 5 epoch
    python notebooks/a_train_v5.py --version v6 --race-oversample 5     # + race 5배 복제
    python notebooks/a_train_v5.py --version v7 --lr 3e-5               # 학습률만 바꿔보기
    python notebooks/a_train_v5.py --version v5_s2 --seed 7             # 제일 좋은 설정을 seed만 바꿔 재확인

⚠️ --version마다 checkpoints/{version}/에 저장 → 번호 안 바꾸면 덮어씀
⚠️ test는 쓰지 않음 (W9에 한 번만)
"""
import argparse
import json
import math
import os
import sys

import numpy as np

# ===== 설정 =====
parser = argparse.ArgumentParser()
parser.add_argument("--version", required=True, help="저장 폴더 이름 (예: v5)")
parser.add_argument("--model", default="beomi/KcELECTRA-base")
parser.add_argument("--pos-weight", choices=["none", "sqrt", "full"], default="sqrt",
                    help="none=v1, full=v3(그대로), sqrt=약하게(기본)")
parser.add_argument("--race-oversample", type=int, default=1, help="race 문장 복제 배수 (1=안 함)")
parser.add_argument("--epochs", type=int, default=5)
parser.add_argument("--lr", type=float, default=2e-5)
parser.add_argument("--batch-size", type=int, default=32)
parser.add_argument("--max-length", type=int, default=64)
parser.add_argument("--seed", type=int, default=42)
args = parser.parse_args()

os.environ.setdefault("HF_HOME", "/nfs/team/hf_cache")
PROJECT_DIR = os.path.realpath(os.path.expanduser("~/project"))
SAVE_DIR = os.path.join(PROJECT_DIR, "checkpoints", args.version)
WARMUP_RATIO = 0.1
WEIGHT_DECAY = 0.01

os.chdir(PROJECT_DIR)
sys.path.insert(0, PROJECT_DIR)
sys.path.insert(0, os.path.join(PROJECT_DIR, "notebooks"))
os.makedirs(SAVE_DIR, exist_ok=True)

import torch
from datasets import Dataset
from transformers import (AutoModelForSequenceClassification, AutoTokenizer,
                          DataCollatorWithPadding, Trainer, TrainingArguments, set_seed)

from a_tune_threshold import crossfit_predict, scores, tune_thresholds
from data.kmhas import LABEL_NAMES, load_kmhas
from models.metrics import evaluate

set_seed(args.seed)
NUM_LABELS = len(LABEL_NAMES)
RACE = LABEL_NAMES.index("race")
print("설정:", vars(args))
print("GPU:", torch.cuda.get_device_name(0) if torch.cuda.is_available() else "없음 (CPU) ⚠️")

# ===== 데이터 =====
train_df, val_df, test_df = load_kmhas()
del test_df

if args.race_oversample > 1:
    race_rows = train_df[train_df["labels"].apply(lambda l: l[RACE] == 1)]
    extra = [race_rows] * (args.race_oversample - 1)
    import pandas as pd
    train_df = pd.concat([train_df, *extra]).sample(frac=1, random_state=args.seed).reset_index(drop=True)
    print(f"race 복제 ×{args.race_oversample}: race {len(race_rows)}건 → {len(race_rows) * args.race_oversample}건")
print(f"train {len(train_df)} / val {len(val_df)}")

tokenizer = AutoTokenizer.from_pretrained(args.model)


def to_dataset(df):
    ds = Dataset.from_dict({"text": df["text"].tolist(),
                            "labels": [[float(x) for x in l] for l in df["labels"]]})
    return ds.map(lambda b: tokenizer(b["text"], truncation=True, max_length=args.max_length),
                  batched=True, remove_columns=["text"])


train_ds, val_ds = to_dataset(train_df), to_dataset(val_df)
collator = DataCollatorWithPadding(tokenizer=tokenizer)

# ===== 클래스 가중치 =====
y_train = np.array(train_df["labels"].tolist())
pos = y_train.sum(axis=0)
ratio = (len(y_train) - pos) / np.maximum(pos, 1)
if args.pos_weight == "full":
    pw = ratio
elif args.pos_weight == "sqrt":
    pw = np.sqrt(ratio)
else:
    pw = None
pos_weight = torch.tensor(pw, dtype=torch.float) if pw is not None else None
print("train 라벨별 개수:", dict(zip(LABEL_NAMES, pos.astype(int))))
if pw is not None:
    print("pos_weight:", dict(zip(LABEL_NAMES, np.round(pw, 1))))


class WeightedTrainer(Trainer):
    def compute_loss(self, model, inputs, return_outputs=False, **kwargs):
        labels = inputs.pop("labels")
        outputs = model(**inputs)
        loss_fn = torch.nn.BCEWithLogitsLoss(pos_weight=pos_weight.to(outputs.logits.device))
        loss = loss_fn(outputs.logits, labels.float())
        return (loss, outputs) if return_outputs else loss


def sigmoid(x):
    return 1 / (1 + np.exp(-x))


def compute_metrics(eval_pred):
    logits, labels = eval_pred
    r = evaluate(labels, sigmoid(logits), threshold=0.5, show=False)
    out = {"micro_f1": r["micro_f1"], "macro_f1": r["macro_f1"]}
    out.update({f"f1_{k}": v for k, v in r["per_label_f1"].items()})
    return out


# ===== 학습 =====
model = AutoModelForSequenceClassification.from_pretrained(
    args.model, num_labels=NUM_LABELS, problem_type="multi_label_classification",
    id2label=dict(enumerate(LABEL_NAMES)), label2id={n: i for i, n in enumerate(LABEL_NAMES)})

total_steps = math.ceil(len(train_ds) / args.batch_size) * args.epochs
targs = TrainingArguments(
    output_dir=SAVE_DIR,
    num_train_epochs=args.epochs,
    per_device_train_batch_size=args.batch_size,
    per_device_eval_batch_size=args.batch_size * 2,
    learning_rate=args.lr,
    weight_decay=WEIGHT_DECAY,
    warmup_steps=math.ceil(total_steps * WARMUP_RATIO),
    eval_strategy="epoch",
    save_strategy="epoch",
    save_total_limit=2,
    load_best_model_at_end=True,          # 마지막이 아니라 val macro F1 최고 epoch을 남김
    metric_for_best_model="macro_f1",
    greater_is_better=True,
    logging_steps=50,
    fp16=torch.cuda.is_available(),
    seed=args.seed,
    report_to="none",
)
TrainerClass = WeightedTrainer if pos_weight is not None else Trainer
trainer = TrainerClass(model=model, args=targs, train_dataset=train_ds, eval_dataset=val_ds,
                       data_collator=collator, compute_metrics=compute_metrics)
trainer.train()

best_epoch = None
for log in trainer.state.log_history:
    if "eval_macro_f1" in log and trainer.state.best_metric is not None \
            and abs(log["eval_macro_f1"] - trainer.state.best_metric) < 1e-9:
        best_epoch = log.get("epoch")
print(f"가장 좋은 epoch: {best_epoch} (val macro F1 @0.5 = {trainer.state.best_metric:.4f})")

# ===== 평가 + 임계값 튜닝 =====
pred = trainer.predict(val_ds)
val_prob = sigmoid(pred.predictions)
y_val = pred.label_ids.astype(int)

print("\n----- 0.5 고정 -----")
r_fixed = evaluate(y_val, val_prob, threshold=0.5, show=True)
ths = tune_thresholds(val_prob, y_val)
s_cross = scores(y_val, crossfit_predict(val_prob, y_val))
print("\n----- 라벨별 임계값 (교차 추정 = 기록용) -----")
for name, t, f in zip(LABEL_NAMES, ths, s_cross["per_label"]):
    print(f"  {name:10s} 임계값 {t:.2f}  F1 {f:.4f}")
print(f"macro F1 {s_cross['macro']:.4f} | micro F1 {s_cross['micro']:.4f}")

# ===== 저장 =====
FINAL_DIR = os.path.join(SAVE_DIR, "final")
trainer.save_model(FINAL_DIR)
tokenizer.save_pretrained(FINAL_DIR)

config = dict(MODEL_NAME=args.model, MAX_LENGTH=args.max_length, BATCH_SIZE=args.batch_size,
              LR=args.lr, EPOCHS=args.epochs, BEST_EPOCH=best_epoch, SEED=args.seed,
              SAMPLE_SIZE=None, THRESHOLD=0.5, POS_WEIGHT=args.pos_weight,
              RACE_OVERSAMPLE=args.race_oversample, n_train=len(train_ds), n_val=len(val_ds))
json.dump(config, open(os.path.join(FINAL_DIR, "train_config.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)
json.dump({name: float(t) for name, t in zip(LABEL_NAMES, ths)},
          open(os.path.join(FINAL_DIR, "thresholds.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)
json.dump({
    "fixed_0.5": {"micro_f1": float(r_fixed["micro_f1"]), "macro_f1": float(r_fixed["macro_f1"]),
                  "per_label_f1": {k: float(v) for k, v in r_fixed["per_label_f1"].items()}},
    "tuned_crossfit": {"micro_f1": float(s_cross["micro"]), "macro_f1": float(s_cross["macro"]),
                       "per_label_f1": dict(zip(LABEL_NAMES, map(float, s_cross["per_label"])))},
}, open(os.path.join(FINAL_DIR, "val_result.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)

# 노션 모델 기록 표에 붙여넣을 한 줄
setting = (f"KcELECTRA / pos_weight {args.pos_weight} / race×{args.race_oversample} / "
           f"lr {args.lr} / {args.epochs}ep(best {best_epoch}) / seed {args.seed}")
print("\n[노션 모델 기록용]")
print(f"{args.version} | {setting} | @0.5 macro {r_fixed['macro_f1']:.4f} micro {r_fixed['micro_f1']:.4f}"
      f" | 임계값 튜닝 macro {s_cross['macro']:.4f} micro {s_cross['micro']:.4f}"
      f" | race F1 {s_cross['per_label'][RACE]:.4f}")

# 중간 체크포인트 정리 (final만 남김, 용량 절약)
import shutil
for d in os.listdir(SAVE_DIR):
    if d.startswith("checkpoint-"):
        shutil.rmtree(os.path.join(SAVE_DIR, d), ignore_errors=True)
print("저장 완료:", FINAL_DIR)