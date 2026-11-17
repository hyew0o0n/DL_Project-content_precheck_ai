
"""W7 - 한국어 이미지 OCR

별도 PaddleOCR 환경을 실행해 OCR 결과를 반환한다.
반환 형식:
[
    {"bbox": [x1, y1, x2, y2], "text": "...", "conf": 0.95}
]
"""

import json
import os
import subprocess
import sys
from pathlib import Path

# 공용 .venv와 충돌하지 않는 별도 OCR 실행 환경
PADDLE_PYTHON = "/nfs/team/b_ocr_compare/paddle_env/bin/python"
MODEL_CACHE = "/nfs/team/b_ocr_compare/paddlex_cache"
MIN_CONF = 0.3
RESULT_PREFIX = "__OCR_RESULT__="


def run_ocr(image_path: str) -> list[dict]:
    """원본 이미지 픽셀 좌표 기준의 OCR 결과를 반환한다."""
    path = Path(image_path).resolve()

    if not path.is_file():
        raise FileNotFoundError(f"이미지가 없습니다: {path}")

    if not Path(PADDLE_PYTHON).is_file():
        raise RuntimeError(
            f"PaddleOCR 실행 환경이 없습니다: {PADDLE_PYTHON}"
        )

    env = os.environ.copy()
    env["PADDLE_PDX_CACHE_HOME"] = MODEL_CACHE
    env["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"
    env["OMP_NUM_THREADS"] = "1"
    env["MKL_NUM_THREADS"] = "1"
    env["OPENBLAS_NUM_THREADS"] = "1"

    result = subprocess.run(
        [
            PADDLE_PYTHON,
            str(Path(__file__).resolve()),
            "--worker",
            str(path),
        ],
        capture_output=True,
        text=True,
        env=env,
        timeout=240,
        check=False,
    )

    if result.returncode != 0:
        raise RuntimeError(
            "PaddleOCR 실행 오류:\n"
            + result.stderr[-3000:]
            + "\n"
            + result.stdout[-1000:]
        )

    for line in reversed(result.stdout.splitlines()):
        if line.startswith(RESULT_PREFIX):
            return json.loads(line[len(RESULT_PREFIX):])

    raise RuntimeError("PaddleOCR 결과를 받지 못했습니다.")


def _run_worker(image_path: str) -> None:
    """별도 PaddleOCR 환경에서 실제 이미지 인식을 수행한다."""
    import tempfile

    from PIL import Image
    from paddleocr import PaddleOCR

    # 확장자와 실제 파일 형식이 달라도 처리할 수 있도록 변환
    with Image.open(image_path) as image:
        rgb_image = image.convert("RGB")
        width, height = rgb_image.size

        with tempfile.TemporaryDirectory() as temp_dir:
            png_path = Path(temp_dir) / "ocr_input.png"
            rgb_image.save(png_path, format="PNG")

            ocr = PaddleOCR(
                lang="korean",
                ocr_version="PP-OCRv5",
                device="cpu",
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=False,
            )

            predictions = ocr.predict(str(png_path))

            items = []

            for prediction in predictions:
                data = prediction.json
                data = data.get("res", data)

                texts = data.get("rec_texts", [])
                scores = data.get("rec_scores", [])
                boxes = data.get("rec_boxes", [])

                for text, score, box in zip(
                    texts, scores, boxes
                ):
                    text = str(text).strip()
                    conf = float(score)

                    # 빈 글자 및 낮은 신뢰도 제외
                    if not text or conf < MIN_CONF:
                        continue

                    x1, y1, x2, y2 = [
                        int(round(float(v))) for v in box
                    ]

                    # 원본 이미지 영역 안으로 좌표 제한
                    x1 = max(0, min(width, x1))
                    x2 = max(0, min(width, x2))
                    y1 = max(0, min(height, y1))
                    y2 = max(0, min(height, y2))

                    if x1 >= x2 or y1 >= y2:
                        continue

                    items.append({
                        "bbox": [x1, y1, x2, y2],
                        "text": text,
                        "conf": round(conf, 4),
                    })

    # 위쪽에서 아래쪽, 같은 높이라면 왼쪽부터 정렬
    items.sort(
        key=lambda item: (
            item["bbox"][1],
            item["bbox"][0],
        )
    )

    print(
        RESULT_PREFIX
        + json.dumps(items, ensure_ascii=False),
        flush=True,
    )


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--worker":
        _run_worker(sys.argv[2])