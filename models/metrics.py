
"""분류 모델 평가 함수. W4 v1, W5 비교, W6 임계값, W9 최종 평가에서 모두 이 함수를 씀."""
import numpy as np
from sklearn.metrics import f1_score, classification_report
from data.kmhas import LABEL_NAMES, LABEL_KO


def evaluate(y_true, y_prob, threshold=0.5, show=True):
    """y_true: 0/1 (N, 9), y_prob: sigmoid 확률 (N, 9)"""
    y_true = np.asarray(y_true)
    y_pred = (np.asarray(y_prob) >= threshold).astype(int)
    result = {
        "micro_f1": f1_score(y_true, y_pred, average="micro", zero_division=0),
        "macro_f1": f1_score(y_true, y_pred, average="macro", zero_division=0),
        "per_label_f1": dict(zip(LABEL_NAMES,
                                 f1_score(y_true, y_pred, average=None, zero_division=0))),
    }
    if show:
        names = [f"{en}({ko})" for en, ko in zip(LABEL_NAMES, LABEL_KO)]
        print(classification_report(y_true, y_pred, target_names=names, zero_division=0))
        print(f"micro F1 {result['micro_f1']:.4f} | macro F1 {result['macro_f1']:.4f}")
    return result
