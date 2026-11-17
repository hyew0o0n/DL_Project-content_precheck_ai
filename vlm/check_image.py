"""VLM 이미지 검수 (기획안 3-2 / W7 A)

Gemini에 이미지를 넣어 OCR·얼굴 검출로 못 잡는 두 가지를 찾는다.
    - sensitive.historical_symbol : 역사·외교 민감 상징 (욱일기 등)
    - rights.ip                   : 타사 로고·캐릭터 (저작권·상표)

판정은 항상 "검토 필요" (VLM은 없는 걸 있다고 할 수 있음 → 사람이 확인).
위치(bbox)는 VLM이 부정확할 수 있어서 이미지 전체(None)로 둔다.
정책 근거는 연결하지 않음 (11/16 결정): evidence=[], "~가 감지됐어요. 유의해주세요" 안내만.
→ pipeline.run_image가 VLM finding은 explain_findings(RAG·LLM)에 넘기지 않음.

사용법
    from vlm.check_image import check_image
    findings = check_image("/nfs/team/data/images/I6.jpg")

단독 실행 (레퍼런스 이미지 확인용)
    python -m vlm.check_image /nfs/team/data/images/I6.jpg /nfs/team/data/images/I10.jpg
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Literal

from PIL import Image
from pydantic import BaseModel, Field

from llm.client import generate

MAX_SIDE = 1024        # 긴 쪽을 이 크기로 줄여서 보냄 (토큰 절약)
MIN_CONF = 0.5         # 이 값 미만은 버림 (대조군 I10으로 조정)
MAX_ITEMS = 3          # 한 이미지에서 최대 finding 수
MAX_RATE_RETRY = 3     # 429 재시도
BACKOFF_SEC = 5

# type → (category, subtype, 화면 이름, 안내 문구, 확인 질문)
# 안내 문구의 {desc} = VLM이 적은 위치·모양 설명
TYPE_INFO = {
    "historical_symbol": (
        "sensitive", "historical_symbol", "역사·외교 민감 상징",
        "역사·외교적으로 민감한 상징으로 보이는 요소가 감지됐어요 ({desc}). 게시 전에 유의해 주세요. 검토가 필요해요.",
        "의도한 디자인인가요? 특정 역사·국가를 떠올리게 할 수 있어 게시해도 괜찮은지 확인해주세요.",
    ),
    "ip": (
        "rights", "ip", "타사 로고·캐릭터",
        "다른 회사의 로고나 캐릭터로 보이는 요소가 감지됐어요 ({desc}). 게시 전에 유의해 주세요. 검토가 필요해요.",
        "사용 권한(라이선스·협찬 계약)이 있는지 확인해주세요.",
    ),
}


# ───────────── VLM 출력 모양 (generate의 schema로 강제) ─────────────
class VLMItem(BaseModel):
    type: Literal["historical_symbol", "ip"] = Field(description="historical_symbol 또는 ip")
    description: str = Field(description="무엇이 어디에 보이는지 한 문장 (한국어)")
    confidence: float = Field(description="0.0–1.0, 확실할수록 높게")


class VLMResult(BaseModel):
    items: list[VLMItem] = Field(description="찾은 요소. 없으면 빈 리스트")


PROMPT = """너는 광고·SNS 이미지 사전 검수 도우미야. 이미지를 보고 아래 두 종류만 찾아줘.

1. historical_symbol: 역사·외교적으로 민감한 상징
   - 예: 욱일기(붉은 원에서 햇살 줄기가 사방으로 뻗는 무늬), 나치 하켄크로이츠, 특정 참사·전쟁을 조롱하는 이미지
   - 주의: 일본 국기(일장기, 흰 바탕에 붉은 원만 있음)나 평범한 햇살·노을 무늬는 해당하지 않아. 줄기 무늬가 붉은 원에서 뻗어 나와 욱일기처럼 보일 때만 적어.
2. ip: 다른 회사·브랜드의 로고, 상표, 유명 캐릭터
   - 예: 스포츠 브랜드 로고, 유명 애니메이션·게임 캐릭터, 다른 회사 제품 상표
   - 광고하는 상품 자체의 브랜드처럼 보이면 confidence를 낮게(0.3 이하) 적어.

규칙
- 이미지에 실제로 보이는 것만 적어. 추측으로 만들어내지 마.
- 글자(문구)·사람 얼굴 자체는 다른 단계에서 검사하니까 적지 마.
- description은 "왼쪽 위 배경에 붉은 햇살 무늬" 처럼 위치와 모양을 짧게. 브랜드 이름은 확실할 때만 적어.
- 해당하는 게 없으면 items를 빈 리스트로.
"""


def _load(image) -> Image.Image:
    img = image if isinstance(image, Image.Image) else Image.open(image)
    img = img.convert("RGB")
    w, h = img.size
    scale = MAX_SIDE / max(w, h)
    if scale < 1:
        img = img.resize((round(w * scale), round(h * scale)))
    return img


def _is_rate_limit(e: Exception) -> bool:
    msg = str(e)
    return getattr(e, "code", None) == 429 or "429" in msg or "RESOURCE_EXHAUSTED" in msg


def ask_vlm(image) -> dict | None:
    """VLM 원본 응답 {"items": [...]} 또는 실패 시 None."""
    img = _load(image)
    parse_fail = rate_fail = 0
    while True:
        try:
            out = generate(PROMPT, schema=VLMResult, image=img)
            return VLMResult(**out).model_dump()
        except Exception as e:  # noqa: BLE001 - 데모가 멈추지 않게
            if _is_rate_limit(e) and rate_fail < MAX_RATE_RETRY:
                wait = BACKOFF_SEC * (2 ** rate_fail)
                print(f"[vlm] 호출 제한(429) → {wait}초 후 재시도")
                time.sleep(wait)
                rate_fail += 1
            elif not _is_rate_limit(e) and parse_fail < 1:
                print(f"[vlm] 응답 오류 → 1회 재시도 ({type(e).__name__}: {str(e)[:80]})")
                parse_fail += 1
            else:
                print(f"[vlm] VLM 실패, 이미지 판단 생략 ({type(e).__name__}: {str(e)[:80]})")
                return None


def to_findings(raw: dict | None, min_conf: float = MIN_CONF) -> list[dict]:
    """VLM 응답 → v0.3 finding 리스트 (id·risk는 pipeline이 채움)."""
    if not raw:
        return []
    items = [it for it in raw.get("items", []) if it.get("confidence", 0) >= min_conf
             and it.get("type") in TYPE_INFO]
    items.sort(key=lambda it: -it["confidence"])

    findings = []
    for it in items[:MAX_ITEMS]:
        category, subtype, label, message, question = TYPE_INFO[it["type"]]
        conf = round(float(it["confidence"]), 4)
        desc = it["description"].strip().rstrip(".")
        findings.append({
            "category": category,
            "subtype": subtype,
            "label": label,
            "verdict": "검토 필요",
            "confidence": conf,
            "source": "vlm",
            "location": {
                "modality": "image",
                "bbox": None,                       # 이미지 전체 (VLM 위치는 부정확)
                "description": desc,
            },
            "evidence": [],                         # 정책 근거 연결 안 함
            "explain_status": "vlm_notice_only",
            "message": message.format(desc=desc),
            "review_question": question,
            "suggestion": None,
        })
    return findings


def check_image(image, min_conf: float = MIN_CONF) -> list[dict]:
    """이미지 경로 또는 PIL.Image → finding 리스트. 실패하면 []."""
    return to_findings(ask_vlm(image), min_conf=min_conf)


if __name__ == "__main__":
    import json
    for p in sys.argv[1:]:
        raw = ask_vlm(p)
        print(f"\n=== {Path(p).name} ===")
        print("raw:", json.dumps(raw, ensure_ascii=False))
        print("findings:", json.dumps(to_findings(raw), ensure_ascii=False, indent=1))