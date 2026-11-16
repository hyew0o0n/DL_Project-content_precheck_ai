"""라벨별 임계값 튜닝 (학습 없음) — 이미 학습된 체크포인트(v1, v3 등)에 바로 적용

왜?  지금은 9개 라벨 모두 0.5로 자르는데, race(인종)처럼 데이터가 적은 라벨은
     확률이 0.5까지 잘 안 올라가서 F1이 0이 됨 (v1 race F1 0.00).
     라벨마다 val에서 가장 좋은 기준값을 찾으면 재학습 없이 macro F1이 오를 수 있음.

실행 (서버, ~/project에서):
    python notebooks/a_tune_threshold.py --versions v1 v3

결과:
    - 화면: 라벨별 F1 (0.5 고정 vs 튜닝) + macro/micro
    - checkpoints/v{번호}/final/thresholds.json  ← 라벨별 임계값 (predict.py에서 쓸 값)
    - results/a_threshold_tuning.md              ← 노션 모델 기록에 옮길 표

⚠️ 점수 해석:
    val로 고른 임계값을 같은 val에서 재면 점수가 부풀려짐.
    그래서 "공정한 점수"는 val을 반으로 나눠 [A로 고르고 B에서 재기 + B로 고르고 A에서 재기]로 계산함 (교차 추정).
    노션 기록 표에는 이 교차 추정 값을 적을 것. 진짜 최종 점수는 W9 test에서 한 번만.
"""
import argparse
import json
import os
import sys

import numpy as np
from sklearn.metrics import f1_score

PROJECT_DIR = os.path.realpath(os.path.expanduser("~/project"))
GRID = np.round(np.arange(0.05, 0.951, 0.01), 2)   # 0.05 ~ 0.95, 0.01 간격


# ---------- 임계값 튜닝 함수 (학습 노트북에서도 import해서 씀) ----------

def tune_thresholds(probs, y, grid=GRID):
    """라벨마다 F1이 가장 높은 임계값. 동점이면 0.5에 가까운 값 (덜 극단적인 쪽)"""
    probs, y = np.asarray(probs), np.asarray(y)
    ths = np.zeros(y.shape[1])
    for j in range(y.shape[1]):
        scores = np.array([f1_score(y[:, j], probs[:, j] >= t, zero_division=0) for t in grid])
        best = scores.max()
        cands = grid[scores >= best - 1e-9]
        ths[j] = cands[np.argmin(np.abs(cands - 0.5))]
    return ths


def crossfit_predict(probs, y, seed=42):
    """val을 반으로 나눠 서로의 임계값으로 예측 → 부풀림 없는 예측값"""
    probs, y = np.asarray(probs), np.asarray(y)
    rng = np.random.default_rng(seed)
    idx = rng.permutation(len(y))
    a, b = idx[: len(y) // 2], idx[len(y) // 2:]
    pred = np.zeros_like(y)
    pred[b] = probs[b] >= tune_thresholds(probs[a], y[a])
    pred[a] = probs[a] >= tune_thresholds(probs[b], y[b])
    return pred


def scores(y, pred):
    return {
        "macro": f1_score(y, pred, average="macro", zero_division=0),
        "micro": f1_score(y, pred, average="micro", zero_division=0),
        "per_label": f1_score(y, pred, average=None, zero_division=0),
    }


def report(version, probs, y, label_names):
    """0.5 고정 / 튜닝(같은 val, 낙관적) / 교차 추정(공정) 세 가지 점수 + 라벨별 표"""
    ths = tune_thresholds(probs, y)
    s_fixed = scores(y, probs >= 0.5)
    s_same = scores(y, probs >= ths)
    s_cross = scores(y, crossfit_predict(probs, y))

    lines = [f"### {version}", "",
             "| 라벨 | val 개수 | 임계값 | F1 @0.5 | F1 튜닝(교차 추정) |",
             "|---|---:|---:|---:|---:|"]
    for j, name in enumerate(label_names):
        lines.append(f"| {name} | {int(y[:, j].sum())} | {ths[j]:.2f} | "
                     f"{s_fixed['per_label'][j]:.4f} | {s_cross['per_label'][j]:.4f} |")
    lines += ["",
              "| 방식 | macro F1 | micro F1 |", "|---|---:|---:|",
              f"| 0.5 고정 (기존 기록과 같은 값) | {s_fixed['macro']:.4f} | {s_fixed['micro']:.4f} |",
              f"| **라벨별 임계값 (교차 추정, 기록용)** | **{s_cross['macro']:.4f}** | **{s_cross['micro']:.4f}** |",
              f"| 라벨별 임계값 (같은 val, 낙관적·참고용) | {s_same['macro']:.4f} | {s_same['micro']:.4f} |",
              ""]
    text = "\n".join(lines)
    print(text)
    return ths, text


# ---------- 체크포인트로 val 확률 구하기 ----------

def get_val_probs(ckpt_dir, texts, max_len=64, batch_size=128):
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    device = "cuda" if torch.cuda.is_available() else "cpu"
    tok = AutoTokenizer.from_pretrained(ckpt_dir)
    model = AutoModelForSequenceClassification.from_pretrained(ckpt_dir).to(device).eval()
    out = []
    with torch.no_grad():
        for i in range(0, len(texts), batch_size):
            enc = tok(texts[i:i + batch_size], truncation=True, max_length=max_len,
                      padding=True, return_tensors="pt").to(device)
            out.append(torch.sigmoid(model(**enc).logits).float().cpu().numpy())
    del model
    if device == "cuda":
        torch.cuda.empty_cache()
    return np.concatenate(out)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--versions", nargs="+", default=["v1", "v3"])
    args = parser.parse_args()

    os.environ.setdefault("HF_HOME", "/nfs/team/hf_cache")
    os.chdir(PROJECT_DIR)
    sys.path.insert(0, PROJECT_DIR)
    from data.kmhas import LABEL_NAMES, load_kmhas

    _, val_df, test_df = load_kmhas()
    del test_df                                   # test는 W9 최종 평가 때만
    texts = val_df["text"].tolist()
    y = np.array(val_df["labels"].tolist())

    md = ["# 라벨별 임계값 튜닝 (학습 없음)", "",
          "- 데이터: K-MHaS validation (test 사용 안 함)",
          "- 임계값 후보: 0.05~0.95 (0.01 간격), 라벨마다 F1 최대값 선택",
          "- **기록용 점수 = 교차 추정** (val을 반으로 나눠 서로의 임계값으로 평가)", ""]

    for v in args.versions:
        ckpt = os.path.join(PROJECT_DIR, "checkpoints", v, "final")
        if not os.path.isdir(ckpt):
            print(f"[건너뜀] {ckpt} 없음")
            continue
        cfg_path = os.path.join(ckpt, "train_config.json")
        cfg = json.load(open(cfg_path, encoding="utf-8")) if os.path.exists(cfg_path) else {}
        max_len = int(cfg.get("MAX_LENGTH", cfg.get("max_length", 64)))

        print(f"\n===== {v} ({ckpt}) =====")
        probs = get_val_probs(ckpt, texts, max_len=max_len)
        ths, text = report(v, probs, y, LABEL_NAMES)
        md.append(text)

        out = {name: float(t) for name, t in zip(LABEL_NAMES, ths)}
        with open(os.path.join(ckpt, "thresholds.json"), "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        print(f"저장: {os.path.join(ckpt, 'thresholds.json')}")

    os.makedirs("results", exist_ok=True)
    with open("results/a_threshold_tuning.md", "w", encoding="utf-8") as f:
        f.write("\n".join(md))
    print("\n저장: results/a_threshold_tuning.md")


if __name__ == "__main__":
    main()