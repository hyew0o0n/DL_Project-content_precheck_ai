
"""W8 - 영상에서 1fps 프레임 추출"""

import json
import math
import subprocess
import tempfile
from pathlib import Path


MAX_DURATION = 60.0
VIDEO_EXTENSIONS = {".mp4", ".mov"}


def get_video_duration(video_path: str) -> float:
    """ffprobe로 영상 길이를 초 단위로 반환한다."""
    path = Path(video_path).resolve()

    if not path.is_file():
        raise FileNotFoundError(f"영상 파일이 없습니다: {path}")

    if path.suffix.lower() not in VIDEO_EXTENSIONS:
        raise ValueError("MP4 또는 MOV 영상만 지원합니다.")

    result = subprocess.run(
        [
            "ffprobe",
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=codec_type:format=duration",
            "-of", "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )

    info = json.loads(result.stdout)

    if not info.get("streams"):
        raise ValueError("영상 스트림이 없습니다.")

    try:
        duration = float(info["format"]["duration"])
    except (KeyError, ValueError, TypeError):
        raise ValueError("영상 길이를 확인할 수 없습니다.")

    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("영상 길이가 올바르지 않습니다.")

    return duration


def extract_frames(
    video_path: str,
    output_dir: str | Path | None = None,
) -> list[dict]:
    """1초당 1장을 추출하고 시간과 프레임 경로를 반환한다.

    반환 예시:
    [
        {"t": 0, "path": ".../f_0000.jpg"},
        {"t": 1, "path": ".../f_0001.jpg"}
    ]

    output_dir을 생략하면 임시 폴더를 생성한다.
    사용이 끝난 프레임은 호출하는 쪽에서 정리해야 한다.
    """
    path = Path(video_path).resolve()
    duration = get_video_duration(str(path))

    if duration > MAX_DURATION:
        raise ValueError(
            f"60초 이하 영상만 지원합니다. 현재: {duration:.2f}초"
        )

    if output_dir is None:
        output = Path(tempfile.mkdtemp(prefix="w8_frames_"))
    else:
        output = Path(output_dir).resolve()
        output.mkdir(parents=True, exist_ok=True)

    # 기존 프레임을 덮어쓰거나 잘못된 결과와 섞지 않음
    if list(output.glob("f_*.jpg")):
        raise FileExistsError(
            f"프레임 파일이 이미 있는 폴더입니다: {output}"
        )

    pattern = output / "f_%04d.jpg"

    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel", "error",
        "-nostdin",
        "-i", str(path),
        "-map", "0:v:0",
        "-vf", "fps=fps=1:start_time=0:round=near",
        "-frames:v", "60",
        "-q:v", "3",
        "-start_number", "0",
        "-y",
        str(pattern),
    ]

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=180,
    )

    if result.returncode != 0:
        raise RuntimeError(
            "FFmpeg 프레임 추출 실패:\n" + result.stderr[-2000:]
        )

    files = sorted(output.glob("f_*.jpg"))

    if not files:
        raise RuntimeError("추출된 프레임이 없습니다.")

    frames = [
        {"t": i, "path": str(frame_path)}
        for i, frame_path in enumerate(files)
    ]

    return frames