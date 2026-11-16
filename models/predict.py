"""위반 유형 분류기 예측 → 출력 JSON v0.2 findings

사용:
    from models.predict import predict
    findings = predict("문장1. 문장2")   # list[dict], 문제 없으면 []

- 문장 단위로 나눠 분류하고, 임계값을 넘은 라벨마다 finding 1개를 만든다.
- 라벨 → (category, subtype, hate_target) 변환은 data/kmhas.py의 LABEL_MAP을 따른다.
- 분류기는 단어 위치를 못 짚으므로 location.span = 그 문장의 시작·끝.
- evidence·message는 비워둔다 (RAG·LLM 단계가 채움). id는 파이프라인에서 다시 매겨도 됨.
"""
import json
import re
from pathlib import Path

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from data.kmhas import LABEL_KO, LABEL_MAP, LABEL_NAMES

ROOT = Path(__file__).resolve().parent.parent           # ~/project
CKPT_DIR = ROOT / "checkpoints" / "v5" / "final"        # 새 버전을 쓰려면 여기만 바꿈
DEFAULT_REVIEW_THRESHOLD = 0.4                          # W6 validation 실험으로 선택
DEFAULT_VIOLATION_THRESHOLD = 0.8                       # W6 validation 실험으로 선택
DEFAULT_THRESHOLD = DEFAULT_REVIEW_THRESHOLD             # 기존 import와의 호환용
DEFAULT_MAX_LENGTH = 64                                 # W3 토큰 길이 95% 지점 37 → 64

POLITICAL_QUESTION = "정치적으로 해석될 수 있는 표현이 있습니다."
HARMFUL_REVIEW_QUESTION = "혐오·욕설 표현일 가능성이 있어 사람의 확인이 필요합니다."
SUBTYPE_LABEL = {"profanity": "욕설·비속어", "political": "정치적 표현"}

_model = _tok = _cfg = None
_device = "cuda" if torch.cuda.is_available() else "cpu"


def _cfg_get(cfg, key, default):
    """train_config.json의 키 이름이 대소문자 어느 쪽이어도 읽기"""
    for k in (key, key.upper(), key.lower()):
        if k in cfg:
            return cfg[k]
    return default


def _load():
    """모델은 처음 한 번만 불러와서 재사용"""
    global _model, _tok, _cfg
    if _model is None:
        cfg_path = CKPT_DIR / "train_config.json"
        _cfg = json.loads(cfg_path.read_text(encoding="utf-8")) if cfg_path.exists() else {}
        _tok = AutoTokenizer.from_pretrained(CKPT_DIR)
        _model = AutoModelForSequenceClassification.from_pretrained(CKPT_DIR).to(_device).eval()
        assert _model.config.num_labels == len(LABEL_NAMES), "체크포인트 라벨 수가 9개가 아님"
    return _model, _tok, _cfg


_SENT_RE = re.compile(r"[^.!?…\n]+[.!?…]*")


def split_sentences(text):
    """문장 경계(. ! ? … 줄바꿈)로 나눠 [(시작, 끝), ...] 반환. 끝은 미포함, 앞뒤 공백 제외"""
    spans = []
    for m in _SENT_RE.finditer(text):
        s, e = m.span()
        seg = m.group()
        s += len(seg) - len(seg.lstrip())
        e -= len(seg) - len(seg.rstrip())
        if e > s:
            spans.append((s, e))
    return spans


def _risk(verdict, conf):
    """v0.2 3-4 위험도 계산식"""
    return round(60 + 40 * conf) if verdict == "위반" else round(20 + 40 * conf)


def _make_finding(name, conf, s, e, sent, verdict):
    category, subtype, target = LABEL_MAP[name]
    if subtype == "hate":
        label = f"혐오 표현 (대상: {LABEL_KO[LABEL_NAMES.index(name)]})"
    else:
        label = SUBTYPE_LABEL[subtype]

    f = {"id": "", "category": category, "subtype": subtype}
    if target is not None:
        f["hate_target"] = target
    f.update({
        "label": label,
        "verdict": verdict,
        "confidence": round(conf, 4),
        "risk": _risk(verdict, conf),
        "source": "classifier",
        "location": {"modality": "text", "span": [s, e], "text": sent},
        "evidence": [],
        "message": "",
        "review_question": (
            POLITICAL_QUESTION
            if subtype == "political"
            else HARMFUL_REVIEW_QUESTION
            if verdict == "검토 필요"
            else None
        ),
        "suggestion": None,
    })
    return f


@torch.no_grad()
def predict(text, threshold=None, review_threshold=None, violation_threshold=None):
    model, tok, cfg = _load()

    # threshold를 명시한 기존 호출은 예전 단일 임계값 방식과 호환한다.
    if threshold is not None:
        review_threshold = float(threshold)
        violation_threshold = float(threshold)
    else:
        if review_threshold is None:
            review_threshold = float(
                _cfg_get(cfg, "review_threshold", DEFAULT_REVIEW_THRESHOLD)
            )
        if violation_threshold is None:
            violation_threshold = float(
                _cfg_get(cfg, "violation_threshold", DEFAULT_VIOLATION_THRESHOLD)
            )

    if not (0.0 <= review_threshold <= violation_threshold <= 1.0):
        raise ValueError(
            "threshold는 0~1 범위에서 review_threshold <= "
            "violation_threshold여야 합니다."
        )

    max_len = int(_cfg_get(cfg, "max_length", DEFAULT_MAX_LENGTH))

    spans = split_sentences(text)
    if not spans:
        return []
    sents = [text[s:e] for s, e in spans]

    enc = tok(sents, truncation=True, max_length=max_len, padding=True,
              return_tensors="pt").to(_device)
    probs = torch.sigmoid(model(**enc).logits).cpu().tolist()

    findings = []
    for (s, e), sent, p in zip(spans, sents, probs):
        for i, name in enumerate(LABEL_NAMES):
            # not_hate는 finding을 만들지 않음
            if LABEL_MAP[name] is None:
                continue

            conf = p[i]

            # review threshold 미만은 통과 → finding 없음
            if conf < review_threshold:
                continue

            _, subtype, _ = LABEL_MAP[name]

            # 정치 표현은 확률이 높아도 자동 위반으로 단정하지 않음
            if subtype == "political":
                verdict = "검토 필요"
            # 혐오·욕설은 두 경계값으로 3단계 판정
            elif conf >= violation_threshold:
                verdict = "위반"
            else:
                verdict = "검토 필요"

            findings.append(
                _make_finding(name, conf, s, e, sent, verdict)
            )

    for n, f in enumerate(findings, 1):
        f["id"] = f"f{n}"
    return findings