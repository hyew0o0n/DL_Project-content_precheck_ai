"""텍스트 MVP 통합 파이프라인.

흐름:
PII 규칙 → 분류기 → 광고 규칙/광고성 감지 → RAG + LLM 설명 → 최종 JSON (v0.3)

v0.3 = v0.2 + evidence[].excerpt, evidence[].applies_to (rag/search.py가 채움)

[W7] 이미지 분기 (run_image / run_file)
OCR 글자 → 위 텍스트 검수 그대로 + 얼굴 검출 + VLM(상징·로고) → 같은 모양의 JSON
- vision/ocr.py, vision/face.py, utils/dates.py(B 담당)가 아직 없으면 그 단계만 건너뜀
"""

import time                      # [추가] meta.elapsed_ms
import uuid                      # [추가] input.id
from datetime import date        # [추가] meta.policy_kb_version
from pathlib import Path         # [추가]

from rules.pii import detect_pii
from rules.ad_patterns import check_ad
from models.predict import predict
from llm.explain import explain_findings

# [W7] B 모듈은 아직 없을 수 있음 → 없으면 해당 단계만 건너뜀 (합의한 형식은 노션 W7 형식 ①·②)
try:
    from vision.ocr import run_ocr
except ImportError:
    run_ocr = None
try:
    from vision.face import detect_faces
except ImportError:
    detect_faces = None
try:
    from vlm.check_image import check_image
except ImportError:
    check_image = None
try:
    from utils.dates import get_reference_date, check_special_day
except ImportError:
    get_reference_date = check_special_day = None


SCHEMA_VERSION = "0.3"                                          # [추가]
KB_PATH = Path(__file__).resolve().parent / "rag" / "policy_kb.jsonl"   # [추가]

VERDICT_ORDER = {
    "통과": 0,
    "검토 필요": 1,
    "위반": 2,
}


def _risk(verdict: str, confidence: float) -> int:
    """v0.2 3-4 위험도 계산식."""
    if verdict == "위반":
        return round(60 + 40 * confidence)
    if verdict == "검토 필요":
        return round(20 + 40 * confidence)
    return 0


def _normalize_findings(findings: list[dict]) -> list[dict]:
    """서로 다른 모듈의 finding을 v0.2 공통 모양으로 맞춘다."""
    normalized = []

    for i, finding in enumerate(findings, 1):
        f = dict(finding)

        f["id"] = f"f{i}"
        f.setdefault("evidence", [])
        f.setdefault("message", "")
        f.setdefault("review_question", None)
        f.setdefault("suggestion", None)

        if "risk" not in f:
            f["risk"] = _risk(
                f.get("verdict", "통과"),
                float(f.get("confidence", 0.0)),
            )

        normalized.append(f)

    return normalized


def _overall_verdict(findings: list[dict]) -> str:
    """findings 중 가장 심한 판정을 전체 verdict로 사용."""
    if not findings:
        return "통과"

    return max(
        (f.get("verdict", "통과") for f in findings),
        key=lambda verdict: VERDICT_ORDER.get(verdict, 0),
    )


# [추가] 한 줄 요약 — 예: "과대·과장 광고 1건, 협찬·대가성 표시 누락 1건"
def _summary(findings: list[dict]) -> str:
    if not findings:
        return "발견된 문제가 없어요"

    counts = {}
    for f in findings:
        label = f.get("label", f.get("subtype", "기타"))
        counts[label] = counts.get(label, 0) + 1

    return ", ".join(f"{label} {n}건" for label, n in counts.items())


# [추가] 정책 KB(JSONL)를 마지막으로 만든 날짜
def _policy_kb_version() -> str:
    try:
        return date.fromtimestamp(KB_PATH.stat().st_mtime).isoformat()
    except OSError:
        return ""


def run_pipeline(text: str, purpose: str = "none", input_id: str | None = None,
                 post_date: str | None = None) -> dict:   # [W7] post_date 추가 (선택)
    """글 하나를 검사하고 텍스트 MVP 최종 JSON을 반환한다."""
    if not isinstance(text, str):
        raise TypeError("text는 문자열이어야 합니다.")

    t0 = time.time()   # [추가]

    # 1. 광고성 감지를 먼저 수행한다.
    ad = check_ad(text, purpose)

    # 2. 규칙 + 분류기 + 광고 규칙 finding을 합친다.
    findings = (
        detect_pii(text)
        + predict(text)
        + ad["findings"]
    )

    # 3. id·risk 등 공통 필드를 맞춘다.
    findings = _normalize_findings(findings)

    # 4. 광고성 여부를 반영해 RAG 근거 검색 + LLM 설명을 붙인다.
    ref_date, special_day = _date_info(post_date)   # [W7] / [W8] 근거 검색에도 같은 기준 날짜 사용
    findings = explain_findings(
        text,
        findings,
        ad_detected=ad["ad_signal"]["detected"],
        ref_date=ref_date,
    )

    # 5. 최종 출력에는 내부 디버그용 rule_id를 제거한다.
    for finding in findings:
        finding.pop("rule_id", None)
        finding.pop("search_types", None)

    # 6. LLM 단계에서 판정이 변경될 수 있으므로 마지막에 전체 판정을 계산한다.
    verdict = _overall_verdict(findings)
    risk_score = max(
        (int(f.get("risk", 0)) for f in findings),
        default=0,
    )

    return {
        "schema_version": SCHEMA_VERSION,                         # [추가]
        "input": {                                                # [추가]
            "id": input_id or f"text_{uuid.uuid4().hex[:8]}",
            "media_type": "text",
            "purpose": purpose,
            "post_date": ref_date,                                # [W7]
        },
        "special_day": special_day,                               # [W7]
        "verdict": verdict,
        "risk_score": risk_score,
        "ad_signal": ad["ad_signal"],
        "summary": _summary(findings),                            # [추가]
        "findings": findings,
        "meta": {                                                 # [추가]
            "policy_kb_version": _policy_kb_version(),
            "elapsed_ms": round((time.time() - t0) * 1000),
        },
    }


# ═══════════════════════════════════════════════════════════════
# [W7] 게시 예정일 · 특별한 날 (utils/dates.py = B, 없으면 날짜만 채움)
# ═══════════════════════════════════════════════════════════════
def _date_info(post_date: str | None) -> tuple[str, dict | None]:
    """(실제로 쓴 기준 날짜 'YYYY-MM-DD', special_day 또는 None)"""
    if get_reference_date is not None:
        try:
            ref = get_reference_date(post_date)
            return ref.isoformat(), check_special_day(ref)
        except Exception as e:  # noqa: BLE001 - 날짜 기능 오류로 검수가 멈추지 않게
            print(f"[pipeline] 날짜 기능 오류, 건너뜀: {e!r}")
    return (post_date or date.today().isoformat()), None


# ═══════════════════════════════════════════════════════════════
# [W7] 이미지 분기
# ═══════════════════════════════════════════════════════════════
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp"}
TEXT_EXT = {".txt"}
VIDEO_EXT = {".mp4", ".mov"}

# 광고가 아닌 이미지에서 인물이 나와도 안내함 (11/16 결정)
#   "always": 항상 안내 / "ad_only": 광고성(목적=광고 또는 광고 패턴 감지)일 때만 안내
FACE_NOTICE = "always"

FACE_LABEL = "인물 감지 (초상권·가상인물 표시)"
FACE_QUESTION = ("인물이 감지됐어요. 초상권 동의를 받았는지, AI로 만든 인물이라면 "
                 "'가상인물' 표시를 했는지 확인해주세요.")


def media_type_of(path: str) -> str:
    ext = Path(path).suffix.lower()
    if ext in IMAGE_EXT:
        return "image"
    if ext in TEXT_EXT:
        return "text"
    if ext in VIDEO_EXT:
        return "video"
    raise ValueError(f"지원하지 않는 형식이에요: {ext}")


def _join_ocr(boxes: list[dict]) -> tuple[str, list[tuple[int, int, dict]]]:
    """OCR 상자들을 한 줄씩 이어 붙인 글 + 상자별 (시작, 끝, 상자) 위치."""
    parts, offsets, cur = [], [], 0
    for b in boxes:
        t = (b.get("text") or "").strip()
        if not t:
            continue
        offsets.append((cur, cur + len(t), b))
        parts.append(t)
        cur += len(t) + 1          # 줄바꿈 1자
    return "\n".join(parts), offsets


def _to_image_location(loc: dict, offsets: list, full_len: int) -> dict:
    """텍스트 finding의 span(이어 붙인 글 기준) → 이미지 위치 (bbox + ocr_text + 상자 기준 span)."""
    s, e = (loc.get("span") or [0, 0])
    new = {"modality": "image", "bbox": None, "text": loc.get("text", "")}
    touched = [(bs, be, b) for bs, be, b in offsets if bs < e and s < be]
    if not touched or (s <= 0 and e >= full_len and len(offsets) > 1):
        return new                  # 글 전체가 대상(예: 표시 누락) → 특정 상자 없음
    bs, be, b = touched[0]
    new.update({
        "bbox": list(b["bbox"]),
        "ocr_text": b["text"].strip(),
        "span": [max(s, bs) - bs, min(e, be) - bs],     # ocr_text 기준
    })
    if len(touched) > 1:            # 여러 줄에 걸친 문장 → 상자 여러 개
        new["bboxes"] = [list(t[2]["bbox"]) for t in touched]
    return new


def _face_finding(faces: list[dict]) -> dict:
    return {
        "category": "ad_rule",
        "subtype": "ai_virtual_human",
        "search_types": ["ai_virtual_human", "portrait"],   # 근거: 가상인물 표시 + 초상권
        "label": FACE_LABEL,
        "verdict": "검토 필요",
        "confidence": round(max(float(f.get("conf", 0.0)) for f in faces), 4),
        "source": "face",
        "location": {
            "modality": "image",
            "bbox": list(faces[0]["bbox"]),
            "bboxes": [list(f["bbox"]) for f in faces],
            "text": f"인물 {len(faces)}명",
        },
        "evidence": [],
        "message": f"이미지에서 인물 {len(faces)}명이 감지됐어요.",
        "review_question": FACE_QUESTION,
        "suggestion": None,
    }


def _step(fn, name, *args, default=None):
    """B 모듈이 없거나 오류가 나도 나머지 단계는 계속 진행."""
    if fn is None:
        return default, "skipped"
    try:
        return fn(*args), "ok"
    except Exception as e:  # noqa: BLE001
        print(f"[pipeline] {name} 오류, 건너뜀: {e!r}")
        return default, f"error: {type(e).__name__}"


def run_image(image_path: str, purpose: str = "none", input_id: str | None = None,
              post_date: str | None = None) -> dict:
    """광고 이미지 1장 → 글자 검수 + 인물 안내 + (VLM) 상징·로고 안내 → v0.3 JSON."""
    from PIL import Image

    t0 = time.time()
    with Image.open(image_path) as im:
        width, height = im.size

    # 1. OCR → 이어 붙인 글로 기존 텍스트 검수 (분류기 문맥 + 호출 1번)
    boxes, ocr_status = _step(run_ocr, "OCR", image_path, default=[])
    full_text, offsets = _join_ocr(boxes)

    ad = check_ad(full_text, purpose)
    text_findings = []
    if full_text.strip():
        text_findings = detect_pii(full_text) + predict(full_text)
    if full_text.strip() or ocr_status == "ok":   # OCR을 못 돌렸으면 '표시 누락'도 판단 보류
        text_findings += ad["findings"]
    for f in text_findings:
        f["location"] = _to_image_location(f.get("location") or {}, offsets, len(full_text))

    # 2. 얼굴 → 인물 안내 (광고성일 때만 / 항상: FACE_NOTICE)
    faces, face_status = _step(detect_faces, "얼굴 검출", image_path, default=[])
    is_ad = purpose == "ad" or ad["ad_signal"]["detected"]
    face_findings = [_face_finding(faces)] if faces and (FACE_NOTICE == "always" or is_ad) else []

    # 3. VLM → 상징·로고
    vlm_findings, vlm_status = _step(check_image, "VLM", image_path, default=[])

    # 4. 합치기 → 공통 필드 → 근거·설명
    #    [W8] 로고·캐릭터(ip)는 상표·저작권 조항을 RAG로 연결 (판정은 항상 검토 필요, 문구는 VLM 것 유지)
    #    민감 상징(historical_symbol)은 근거 행이 없어 지금처럼 안내만
    findings = _normalize_findings(text_findings + face_findings + vlm_findings)
    ref_date, special_day = _date_info(post_date)
    needs_evidence = lambda f: f.get("source") != "vlm" or f.get("subtype") == "ip"
    explained = explain_findings(
        full_text or "(이미지 속 글자 없음)",
        [f for f in findings if needs_evidence(f)],
        ad_detected=ad["ad_signal"]["detected"],
        ref_date=ref_date,
    )
    findings = explained + [f for f in findings if not needs_evidence(f)]   # 안내만 하는 VLM은 맨 뒤
    for f in findings:
        f.pop("rule_id", None)
        f.pop("search_types", None)

    verdict = _overall_verdict(findings)

    return {
        "schema_version": SCHEMA_VERSION,
        "input": {
            "id": input_id or f"img_{uuid.uuid4().hex[:8]}",
            "media_type": "image",
            "file_name": Path(image_path).name,
            "width": width,
            "height": height,
            "purpose": purpose,
            "post_date": ref_date,
        },
        "special_day": special_day,
        "verdict": verdict,
        "risk_score": max((int(f.get("risk", 0)) for f in findings), default=0),
        "ad_signal": ad["ad_signal"],
        "summary": _summary(findings),
        "findings": findings,
        "ocr": [{"bbox": list(b["bbox"]), "text": b["text"], "conf": b.get("conf")} for b in boxes],
        "meta": {
            "policy_kb_version": _policy_kb_version(),
            "elapsed_ms": round((time.time() - t0) * 1000),
            "steps": {"ocr": ocr_status, "face": face_status, "vlm": vlm_status},
            "ocr_text": full_text,
        },
    }


def run_file(path: str, purpose: str = "none", input_id: str | None = None,
             post_date: str | None = None) -> dict:
    """확장자로 형식 판별 → 텍스트 / 이미지 / 영상 분기."""
    kind = media_type_of(path)
    if kind == "image":
        return run_image(path, purpose, input_id, post_date)
    if kind == "text":
        text = Path(path).read_text(encoding="utf-8", errors="ignore")
        return run_pipeline(text, purpose, input_id, post_date)
    if kind == "video":   # [W8] B의 영상 검수 (1fps 프레임 → 이미지 검수 재사용 → 시간 구간 병합)
        from video.run_video import run_video
        return run_video(path, purpose=purpose, input_id=input_id, post_date=post_date)
    raise ValueError(f"지원하지 않는 형식이에요: {kind}")


# app.py 등에서 analyze()라는 이름을 써도 같은 함수가 동작하도록 제공
analyze = run_pipeline
run = run_pipeline   # [추가] app.py는 run → analyze 순서로 찾음