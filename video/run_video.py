
"""W8: 1fps 영상 검수 및 시간 구간 병합.

- 최대 60초 영상에서 1fps 추출
- OCR 매 프레임 실행
- 텍스트 변경 시에만 분류/설명 실행
- 얼굴 검출 매 프레임, 작은 얼굴 후보 제외
- VLM 기본 5초 간격 실행
- 동일 문제의 연속 시간 구간 병합
- 대표 프레임 및 문제 시작 프레임 보존
- VLM 오류 시 검수 미완료 예외 전달
"""

from copy import deepcopy
from pathlib import Path
import shutil
import tempfile
import time
import uuid


def _finding_key(finding: dict) -> tuple:
    """같은 문제인지 비교하기 위한 기준."""
    location = finding.get("location") or {}

    text = (
        location.get("ocr_text")
        or location.get("text")
        or finding.get("message")
        or ""
    )

    normalized_text = " ".join(str(text).split())

    return (
        finding.get("source"),
        finding.get("category"),
        finding.get("subtype"),
        finding.get("verdict"),
        normalized_text,
    )


def merge_frame_results(
    frame_results: list[dict],
    duration: float,
) -> list[dict]:
    """연속된 동일 문제를 하나의 시간 구간으로 병합한다."""
    merged = []
    active = {}

    for item in sorted(
        frame_results,
        key=lambda x: x["t"],
    ):
        t = int(item["t"])
        current = {}

        for finding in item["result"].get("findings", []):
            key = _finding_key(finding)

            if key in current:
                continue

            if key in active:
                index = active[key]
                previous = merged[index]

                if previous["_last_t"] == t - 1:
                    previous["location"]["time"][1] = min(
                        float(duration),
                        float(t + 1),
                    )
                    previous["_last_t"] = t
                    current[key] = index
                    continue

            new_finding = deepcopy(finding)
            location = new_finding.get("location") or {}

            new_finding["location"] = {
                **location,
                "modality": "video",
                "time": [
                    t,
                    min(float(duration), float(t + 1)),
                ],
                "frame_time": t,
            }

            new_finding["_last_t"] = t

            merged.append(new_finding)
            current[key] = len(merged) - 1

        active = current

    for finding in merged:
        finding.pop("_last_t", None)

    return merged


def save_video_previews(
    frames: list[dict],
    findings: list[dict],
) -> tuple[str, str]:
    """영상 대표 프레임과 문제 시작 프레임을 저장한다."""
    if not frames:
        raise ValueError("저장할 영상 프레임이 없습니다.")

    frame_map = {
        int(frame["t"]): Path(frame["path"])
        for frame in frames
    }

    first_t = int(frames[0]["t"])
    times = {first_t}

    for finding in findings:
        location = finding.get("location") or {}
        times.add(
            int(location.get("frame_time", first_t))
        )

    output_dir = Path(
        tempfile.mkdtemp(prefix="w8_video_preview_")
    )

    try:
        saved = {}

        for t in sorted(times):
            source = frame_map.get(t)

            if source is None or not source.is_file():
                raise FileNotFoundError(
                    f"{t}초의 원본 프레임을 찾을 수 없습니다."
                )

            destination = (
                output_dir / f"frame_{t:04d}.jpg"
            )

            shutil.copy2(source, destination)
            saved[t] = str(destination)

        for finding in findings:
            location = finding.get("location") or {}
            t = int(
                location.get("frame_time", first_t)
            )

            finding["location"]["frame_path"] = (
                saved[t]
            )

        return str(output_dir), saved[first_t]

    except Exception:
        shutil.rmtree(
            output_dir,
            ignore_errors=True,
        )
        raise


def plan_frame_checks(
    frame_ocr_results: list[dict],
    vlm_interval: int = 5,
) -> list[dict]:
    """OCR 문구 변화에 따른 검수 실행 계획을 만든다."""
    if vlm_interval < 1:
        raise ValueError(
            "VLM 호출 간격은 1초 이상이어야 합니다."
        )

    plan = []
    previous_text = None

    for item in sorted(
        frame_ocr_results,
        key=lambda x: x["t"],
    ):
        t = int(item["t"])

        text = "\n".join(
            str(box.get("text", "")).strip()
            for box in item.get("ocr", [])
            if str(box.get("text", "")).strip()
        )

        normalized_text = " ".join(text.split())

        text_changed = (
            previous_text is None
            or normalized_text != previous_text
        )

        plan.append({
            "t": t,
            "ocr_text": text,
            "run_text": text_changed,
            "run_face": True,
            "run_vlm": t % vlm_interval == 0,
        })

        previous_text = normalized_text

    return plan


def run_staged_checks(
    frames: list[dict],
    *,
    ocr_fn,
    text_fn,
    face_fn,
    vlm_fn,
    vlm_interval: int = 5,
) -> list[dict]:
    """프레임별 OCR·텍스트·얼굴·VLM 실행을 제어한다."""
    if vlm_interval < 1:
        raise ValueError(
            "VLM 호출 간격은 1 이상이어야 합니다."
        )

    results = []
    previous_text = None
    cached_text_findings = []

    for frame in sorted(
        frames,
        key=lambda x: x["t"],
    ):
        t = int(frame["t"])
        path = frame["path"]

        # 1. OCR은 매 프레임 실행
        boxes = ocr_fn(path)

        full_text = "\n".join(
            str(box.get("text", "")).strip()
            for box in boxes
            if str(box.get("text", "")).strip()
        )

        # 2. 텍스트가 달라진 경우에만 검수
        text_changed = (
            previous_text is None
            or full_text != previous_text
        )

        if text_changed:
            cached_text_findings = text_fn(
                full_text
            )

        # 3. 얼굴 검출은 매 프레임
        face_findings = face_fn(path)

        # 4. VLM은 지정된 간격에 실행
        run_vlm = t % vlm_interval == 0

        if run_vlm:
            try:
                vlm_findings = vlm_fn(path)
            except Exception as exc:
                raise RuntimeError(
                    f"영상 {t}초 VLM 검수 실패: "
                    "전체 영상 판정 미완료"
                ) from exc
        else:
            vlm_findings = []

        results.append({
            "t": t,
            "path": path,
            "ocr": boxes,
            "ocr_text": full_text,
            "text_findings": deepcopy(
                cached_text_findings
            ),
            "face_findings": face_findings,
            "vlm_findings": vlm_findings,
            "run_text": text_changed,
            "run_vlm": run_vlm,
        })

        previous_text = full_text

    return results


def filter_video_faces(
    faces: list[dict],
    min_size: int = 24,
) -> list[dict]:
    """영상에서 작은 얼굴 검출 후보를 제외한다.

    24px 기준은 W8 실험에서 적용한 임시 기준이다.
    """
    filtered = []

    for face in faces:
        bbox = face.get("bbox")

        if not bbox or len(bbox) != 4:
            continue

        x1, y1, x2, y2 = bbox

        width = x2 - x1
        height = y2 - y1

        if width >= min_size and height >= min_size:
            filtered.append(face)

    return filtered


def build_frame_result(
    staged: dict,
    purpose: str = "none",
) -> dict:
    """단계별 결과를 이미지 finding 형식으로 변환한다."""
    import pipeline
    from rules.ad_patterns import check_ad

    boxes = staged.get("ocr", [])

    full_text, offsets = pipeline._join_ocr(
        boxes
    )

    text_findings = deepcopy(
        staged.get("text_findings", [])
    )

    # 현재 프레임의 OCR 좌표 적용
    for finding in text_findings:
        location = finding.get("location") or {}

        if location.get("modality") == "text":
            finding["location"] = (
                pipeline._to_image_location(
                    location,
                    offsets,
                    len(full_text),
                )
            )

    ad_signal = check_ad(
        full_text,
        purpose,
    )["ad_signal"]

    # 작은 얼굴 후보 제외
    faces = filter_video_faces(
        staged.get("face_findings", [])
    )

    is_ad = (
        purpose == "ad"
        or ad_signal["detected"]
    )

    face_findings = []

    if faces and (
        pipeline.FACE_NOTICE == "always"
        or is_ad
    ):
        face_findings = [
            pipeline._face_finding(faces)
        ]

    vlm_findings = deepcopy(
        staged.get("vlm_findings", [])
    )

    findings = pipeline._normalize_findings(
        text_findings
        + face_findings
        + vlm_findings
    )

    for finding in findings:
        finding.pop("rule_id", None)
        finding.pop("search_types", None)

    return {
        "verdict": pipeline._overall_verdict(
            findings
        ),
        "findings": findings,
        "ocr": deepcopy(boxes),
        "ad_signal": ad_signal,
    }


def check_frame_text(
    text: str,
    purpose: str = "none",
    ref_date: str | None = None,
) -> list[dict]:
    """기존 개인정보·분류기·광고 규칙·설명 기능을 사용한다."""
    import pipeline

    if not text.strip():
        return []

    ad = pipeline.check_ad(
        text,
        purpose,
    )

    findings = (
        pipeline.detect_pii(text)
        + pipeline.predict(text)
        + ad["findings"]
    )

    findings = pipeline._normalize_findings(
        findings
    )

    explained = pipeline.explain_findings(
        text,
        findings,
        ad_detected=ad["ad_signal"]["detected"],
        ref_date=ref_date,   # [W8] 게시 예정일 기준으로 근거 조항 시행 상태 판단
    )

    for finding in explained:
        finding.pop("rule_id", None)
        finding.pop("search_types", None)

    return explained


def explain_merged_notices(
    findings: list[dict],
    staged: list[dict],
    ad_detected: bool = False,
    ref_date: str | None = None,
) -> list[dict]:
    """[W8] 병합된 인물(face)·로고(vlm ip) finding에 정책 근거를 붙인다.

    텍스트 finding은 프레임마다 이미 근거가 붙어 있으므로 건너뛴다.
    민감 상징(historical_symbol)은 근거 행이 없어 안내만 유지한다.
    """
    import pipeline

    def needs(f):
        return not f.get("evidence") and (
            f.get("source") == "face"
            or (f.get("source") == "vlm" and f.get("subtype") == "ip")
        )

    targets = [i for i, f in enumerate(findings) if needs(f)]
    if not targets:
        return findings

    to_explain = []
    for i in targets:
        f = deepcopy(findings[i])
        if f.get("source") == "face":
            f["search_types"] = ["ai_virtual_human", "portrait"]
        to_explain.append(f)

    context = "\n".join(
        dict.fromkeys(
            (b.get("text") or "").strip()
            for item in staged
            for b in item.get("ocr", [])
            if (b.get("text") or "").strip()
        )
    ) or "(영상 속 글자 없음)"

    explained = pipeline.explain_findings(
        context,
        to_explain,
        ad_detected=ad_detected,
        ref_date=ref_date,
    )

    result = list(findings)
    for i, f in zip(targets, explained):
        f.pop("rule_id", None)
        f.pop("search_types", None)
        f["location"] = findings[i]["location"]   # 시간 구간·장면 경로 유지
        result[i] = f
    return result


def _collect_ad_signal(
    frame_results: list[dict],
) -> dict:
    """프레임별 광고 신호를 통합한다."""
    signals = [
        item["result"].get("ad_signal")
        or {
            "detected": False,
            "score": 0.0,
        }
        for item in frame_results
    ]

    detected = [
        signal
        for signal in signals
        if signal.get("detected")
    ]

    if detected:
        ad_signal = dict(
            max(
                detected,
                key=lambda signal: signal.get(
                    "score", 0
                ),
            )
        )
    else:
        ad_signal = {
            "detected": False,
            "by": "none",
            "score": 0.0,
        }

    ad_signal["disclosure_found"] = any(
        signal.get("disclosure_found", False)
        for signal in signals
    )

    return ad_signal


def _run_video_staged(
    video_path: str,
    purpose: str = "none",
    input_id: str | None = None,
    post_date: str | None = None,
    *,
    ocr_fn=None,
    text_fn=None,
    face_fn=None,
    vlm_fn=None,
    vlm_interval: int = 5,
) -> dict:
    """1fps 영상 검수를 실행하고 최종 결과를 생성한다."""
    from PIL import Image

    import pipeline
    from video.frames import (
        extract_frames,
        get_video_duration,
    )

    if vlm_interval < 1:
        raise ValueError(
            "VLM 호출 간격은 1초 이상이어야 합니다."
        )

    # 기존 프로젝트 검수 함수 사용
    if ocr_fn is None:
        from vision.ocr import run_ocr
        ocr_fn = run_ocr

    # [W8] 게시 예정일 → 근거 검색 기준 날짜 (텍스트·인물·로고 근거 모두 같은 날짜)
    ref_date, special_day = pipeline._date_info(
        post_date
    )

    if text_fn is None:
        text_fn = lambda text: check_frame_text(
            text,
            purpose=purpose,
            ref_date=ref_date,
        )

    if face_fn is None:
        from vision.face import detect_faces
        face_fn = detect_faces

    if vlm_fn is None:
        from vlm.check_image import check_image
        vlm_fn = check_image

    started = time.time()
    duration = get_video_duration(video_path)

    with tempfile.TemporaryDirectory(
        prefix="w8_video_"
    ) as tmp:

        # 1. 영상 프레임 추출
        frames = extract_frames(
            video_path,
            output_dir=tmp,
        )

        with Image.open(frames[0]["path"]) as image:
            width, height = image.size

        # 2. OCR·텍스트·얼굴·VLM 검수
        staged = run_staged_checks(
            frames,
            ocr_fn=ocr_fn,
            text_fn=text_fn,
            face_fn=face_fn,
            vlm_fn=vlm_fn,
            vlm_interval=vlm_interval,
        )

        # 3. 이미지 결과 형식으로 변환
        frame_results = [
            {
                "t": item["t"],
                "result": build_frame_result(
                    item,
                    purpose=purpose,
                ),
            }
            for item in staged
        ]

        # 4. 동일 문제 시간 구간 병합
        findings = merge_frame_results(
            frame_results,
            duration,
        )

        # 4-1. [W8] 인물·로고(ip) 근거 연결: 병합 후 구간마다 1번만 호출 (이미지 검수와 같은 근거)
        findings = explain_merged_notices(
            findings,
            staged,
            ad_detected=_collect_ad_signal(frame_results)["detected"],
            ref_date=ref_date,
        )

        ocr_results = [
            {
                "t": item["t"],
                "boxes": item["ocr"],
            }
            for item in staged
        ]

        # 5. 임시 프레임 삭제 전 대표 이미지 저장
        preview_dir, representative_frame = (
            save_video_previews(
                frames,
                findings,
            )
        )

    # 6. 영상 전체 결과 계산
    for i, finding in enumerate(findings, 1):
        finding["id"] = f"f{i}"

    verdict = pipeline._overall_verdict(
        findings
    )

    risk_score = max(
        (
            int(f.get("risk", 0))
            for f in findings
        ),
        default=0,
    )

    stage_runs = {
        "ocr": len(staged),
        "text": sum(
            bool(item["run_text"])
            for item in staged
        ),
        "face": len(staged),
        "vlm": sum(
            bool(item["run_vlm"])
            for item in staged
        ),
    }

    return {
        "schema_version": pipeline.SCHEMA_VERSION,
        "input": {
            "id": input_id or (
                f"video_{uuid.uuid4().hex[:8]}"
            ),
            "media_type": "video",
            "file_name": Path(video_path).name,
            "width": width,
            "height": height,
            "duration": duration,
            "fps": 1,
            "purpose": purpose,
            "post_date": ref_date,
            "representative_frame": representative_frame,
        },
        "special_day": special_day,
        "verdict": verdict,
        "risk_score": risk_score,
        "ad_signal": _collect_ad_signal(
            frame_results
        ),
        "summary": pipeline._summary(
            findings
        ),
        "findings": findings,
        "ocr": ocr_results,
        "meta": {
            "policy_kb_version": (
                pipeline._policy_kb_version()
            ),
            "elapsed_ms": round(
                (time.time() - started) * 1000
            ),
            "frame_count": len(staged),
            "fps": 1,
            "mode": "staged",
            "stage_runs": stage_runs,
            "preview_dir": preview_dir,
        },
    }


def run_video(
    video_path: str,
    purpose: str = "none",
    input_id: str | None = None,
    post_date: str | None = None,
    *,
    frame_runner=None,
) -> dict:
    """영상 검수 공개 진입점.

    frame_runner=None이면 실제 단계별 검수를 수행한다.
    frame_runner가 있으면 구조 테스트 방식으로 실행한다.
    """
    if frame_runner is None:
        return _run_video_staged(
            video_path,
            purpose=purpose,
            input_id=input_id,
            post_date=post_date,
        )

    from video.frames import (
        extract_frames,
        get_video_duration,
    )

    import pipeline

    started = time.time()
    duration = get_video_duration(video_path)

    with tempfile.TemporaryDirectory(
        prefix="w8_video_"
    ) as tmp:

        frames = extract_frames(
            video_path,
            output_dir=tmp,
        )

        frame_results = []
        first_result = None

        for frame in frames:
            result = frame_runner(
                frame["path"],
                purpose=purpose,
                input_id=f"frame_{frame['t']:04d}",
                post_date=post_date,
            )

            if not isinstance(result, dict):
                raise TypeError(
                    "프레임 검수 결과는 dict여야 합니다."
                )

            if first_result is None:
                first_result = result

            frame_results.append({
                "t": frame["t"],
                "result": result,
            })

        if first_result is None:
            raise RuntimeError(
                "검수할 프레임이 없습니다."
            )

        findings = merge_frame_results(
            frame_results,
            duration,
        )

        preview_dir, representative_frame = (
            save_video_previews(
                frames,
                findings,
            )
        )

    for i, finding in enumerate(findings, 1):
        finding["id"] = f"f{i}"

    ref_date, special_day = pipeline._date_info(
        post_date
    )

    return {
        "schema_version": first_result.get(
            "schema_version",
            "0.3",
        ),
        "input": {
            **first_result.get("input", {}),
            "id": input_id or (
                f"video_{uuid.uuid4().hex[:8]}"
            ),
            "media_type": "video",
            "file_name": Path(video_path).name,
            "duration": duration,
            "fps": 1,
            "purpose": purpose,
            "post_date": ref_date,
            "representative_frame": representative_frame,
        },
        "special_day": special_day,
        "verdict": pipeline._overall_verdict(
            findings
        ),
        "risk_score": max(
            (
                int(f.get("risk", 0))
                for f in findings
            ),
            default=0,
        ),
        "ad_signal": _collect_ad_signal(
            frame_results
        ),
        "summary": pipeline._summary(
            findings
        ),
        "findings": findings,
        "ocr": [
            {
                "t": item["t"],
                "boxes": item["result"].get(
                    "ocr", []
                ),
            }
            for item in frame_results
        ],
        "meta": {
            "policy_kb_version": (
                first_result.get(
                    "meta", {}
                ).get("policy_kb_version", "")
            ),
            "elapsed_ms": round(
                (time.time() - started) * 1000
            ),
            "frame_count": len(frame_results),
            "fps": 1,
            "mode": "structure_test",
            "preview_dir": preview_dir,
        },
    }
