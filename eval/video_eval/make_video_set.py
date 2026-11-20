"""W8 영상 평가셋 생성: MP4 배경 5개 + 자막 → 10초 영상 10개.

프로젝트 루트에서 실행:
  python eval/video_eval/make_video_set.py

의존성: ffmpeg, ffprobe, Pillow, 같은 폴더의 render_text.py.
배경: data/video_bg/bg01.mp4 ~ bg05.mp4 (사용자 제공, 원본 출처 별도 기록).
기존 결과 보호: 이미 결과 파일이 있으면 덮어쓰지 않음 (--overwrite로 명시).
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
from datetime import date
from pathlib import Path

from render_text import render_text

PROJECT_ROOT = Path(__file__).resolve().parents[2]
VIDEO_SECONDS = 10.0
OUTPUT_WIDTH = 720
OUTPUT_HEIGHT = 1280
OUTPUT_FPS = 15

# 각 길이(0.5초/1초/2초/3초)는 2개씩. 같은 0.5초도
# 1fps의 정수 초 샘플에 걸리는 사례/걸리지 않는 사례를 모두 둔다.
CASES = [
    {"id": "V01", "background": "bg01.mp4", "label": "issue", "issue_type": "pii_phone", "text": "문의 010-1234-5678", "start": 2.25, "duration": 0.5},
    {"id": "V02", "background": "bg02.mp4", "label": "issue", "issue_type": "verbal_abuse", "text": "야, 멍청아. 당장 꺼져.", "start": 4.75, "duration": 0.5},
    {"id": "V03", "background": "bg03.mp4", "label": "issue", "issue_type": "unverified_ad_claim", "text": "먹기만 하면 100% 살이 빠집니다", "start": 2.25, "duration": 1.0},
    {"id": "V04", "background": "bg04.mp4", "label": "issue", "issue_type": "pii_phone", "text": "개인 연락처 010-9876-5432", "start": 5.40, "duration": 1.0},
    {"id": "V05", "background": "bg05.mp4", "label": "issue", "issue_type": "verbal_abuse", "text": "정말 멍청하고 한심해", "start": 1.30, "duration": 2.0},
    {"id": "V06", "background": "bg05.mp4", "label": "issue", "issue_type": "pii_phone", "text": "담당자 연락처 010-4567-8901", "start": 6.40, "duration": 2.0},
    {"id": "V07", "background": "bg03.mp4", "label": "issue", "issue_type": "unverified_ad_claim", "text": "이 상품으로 무조건 100% 수익 보장", "start": 2.50, "duration": 3.0},
    {"id": "V08", "background": "bg04.mp4", "label": "issue", "issue_type": "unverified_medical_claim", "text": "이 약만 먹으면 모든 병이 완치됩니다", "start": 5.70, "duration": 3.0},
    {"id": "V09", "background": "bg01.mp4", "label": "normal", "issue_type": None, "text": "오늘의 풍경을 기록합니다", "start": 3.00, "duration": 2.0},
    {"id": "V10", "background": "bg02.mp4", "label": "normal", "issue_type": None, "text": "맛있는 점심을 먹었어요", "start": 5.00, "duration": 3.0},
]


def probe_duration(path: Path) -> float:
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True,
    )
    duration = float(proc.stdout.strip())
    if not math.isfinite(duration) or duration < VIDEO_SECONDS:
        raise ValueError(f"배경 영상 길이 부족 또는 잘못된 길이: {path} ({duration})")
    return duration


def create_video(background: Path, caption: Path, output: Path, start: float, end: float, fps: int):
    # 영상은 무음, 720x1280, 15fps 기본. bg04 등의 9:16 외 비율은 가운데 크롭.
    # 반투명 PNG를 정확한 구간 [start, end)에만 표시.
    filt = (
        f"[0:v]trim=duration={VIDEO_SECONDS},setpts=PTS-STARTPTS,"
        f"fps={fps},scale={OUTPUT_WIDTH}:{OUTPUT_HEIGHT}:force_original_aspect_ratio=increase,"
        f"crop={OUTPUT_WIDTH}:{OUTPUT_HEIGHT},format=yuv420p[bg];"
        f"[1:v]format=rgba[cap];"
        f"[bg][cap]overlay=0:0:enable='gte(t,{start})*lt(t,{end})':"
        f"shortest=1:format=auto,format=yuv420p[out]"
    )
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
        "-i", str(background),
        "-loop", "1", "-framerate", str(fps), "-i", str(caption),
        "-filter_complex", filt,
        "-map", "[out]", "-an", "-t", str(VIDEO_SECONDS),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "28",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-threads", "2",
        str(output),
    ]
    subprocess.run(cmd, check=True)


def make_set(background_dir: Path, output_dir: Path, fps: int, overwrite: bool = False, resume: bool = False):
    if fps < 1:
        raise ValueError("fps는 1 이상이어야 합니다.")
    videos_dir = output_dir / "videos"
    captions_dir = output_dir / "captions"
    labels_path = output_dir / "labels.json"

    # 일괄 실행 전 기존 결과를 확인하여 실수로 평가셋을 변경하는 것을 막음.
    planned = [videos_dir / f"{case['id']}.mp4" for case in CASES]
    if not overwrite and not resume and (labels_path.exists() or any(x.exists() for x in planned)):
        raise FileExistsError(
            f"기존 평가셋이 있습니다: {output_dir}. 새로 생성하려면 --overwrite 필요"
        )

    backgrounds = {c["background"] for c in CASES}
    for name in sorted(backgrounds):
        path = background_dir / name
        if not path.is_file():
            raise FileNotFoundError(f"배경 영상 없음: {path}")
        probe_duration(path)

    videos_dir.mkdir(parents=True, exist_ok=True)
    captions_dir.mkdir(parents=True, exist_ok=True)

    labels = []
    for case in CASES:
        ident = case["id"]
        start = float(case["start"])
        duration = float(case["duration"])
        end = round(start + duration, 3)
        if not 0 <= start < end <= VIDEO_SECONDS:
            raise ValueError(f"자막 시간이 영상 범위를 벗어남: {ident}")

        caption_path = captions_dir / f"{ident}.png"
        video_path = videos_dir / f"{ident}.mp4"
        # 중단된 생성을 이어갈 때는 재생 가능한 완성본을 건너뜀.
        is_complete = False
        if resume and video_path.is_file() and caption_path.is_file():
            try:
                d = probe_duration(video_path)
                is_complete = abs(d - VIDEO_SECONDS) < 0.1
            except (ValueError, subprocess.CalledProcessError):
                pass
        if not is_complete:
            # 기존 render_text.py의 한글 폰트 설정을 그대로 재사용.
            render_text(case["text"], str(caption_path), width=OUTPUT_WIDTH, height=OUTPUT_HEIGHT)
            create_video(background_dir / case["background"], caption_path, video_path, start, end, fps)
        else:
            print(f"건너뜀 {ident}: 기존 정상 파일", flush=True)

        sample_hits = [t for t in range(int(VIDEO_SECONDS)) if start <= t + 0.5 < end]
        labels.append({
            "id": ident,
            "video": f"videos/{ident}.mp4",
            "background": case["background"],
            "label": case["label"],
            "issue_type": case["issue_type"],
            "caption": case["text"],
            "caption_start_sec": start,
            "caption_end_sec": end,
            "caption_duration_sec": duration,
            "ideal_1fps_sample_times_sec": sample_hits,
            "ideal_1fps_sampling_visible": bool(sample_hits),
            "background_source_url": None,
            "background_license_verified": False,
        })
        print(f"완료 {ident}: {case['label']}, {duration}초, {video_path}", flush=True)

    data = {
        "dataset_name": "W8_synthetic_video_eval_v1",
        "created_date": str(date.today()),
        "video_duration_sec": VIDEO_SECONDS,
        "output_resolution": [OUTPUT_WIDTH, OUTPUT_HEIGHT],
        "output_fps": fps,
        "sampling_assumption": "integer seconds 0..9 at 1fps; actual FFmpeg timestamp rounding should be checked",
        "annotations": "synthetic test-case labels; policy/model output does not necessarily equal the manual issue label",
        "limitations": [
            "This is a small synthetic smoke-test dataset, not an unbiased model performance benchmark.",
            "Pexels/video licensing and individual download URLs must be verified and recorded before distribution.",
            "1fps sampling may miss subtitles shown for less than 1 second.",
            "Background signs, visuals, and faces may also affect a model's predictions.",
        ],
        "counts": {"issue": 8, "normal": 2},
        "items": labels,
    }
    labels_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"정답 데이터: {labels_path}", flush=True)
    return labels_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--background-dir", type=Path, default=PROJECT_ROOT / "data/video_bg")
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "eval/data/video_eval")
    parser.add_argument("--fps", type=int, default=OUTPUT_FPS)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--resume", action="store_true", help="미완성 영상만 이어서 제작")
    args = parser.parse_args()
    make_set(args.background_dir, args.output_dir, args.fps, args.overwrite, args.resume)


if __name__ == "__main__":
    main()
