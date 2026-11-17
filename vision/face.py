
"""W7 - 얼굴 검출

OpenCV YuNet을 사용해 이미지 속 얼굴을 검출한다.

반환 형식:
[
    {"bbox": [x1, y1, x2, y2], "conf": 0.95}
]

얼굴이 검출되지 않으면 []를 반환한다.
"""

import math
import os
from pathlib import Path

import cv2
import numpy as np
from PIL import Image


MODEL_PATH = Path(
    os.environ.get(
        "FACE_DETECTOR_MODEL_PATH",
        "/nfs/team/b_face_models/face_detection_yunet_2023mar.onnx",
    )
)

MIN_CONF = 0.5


def detect_faces(image_path: str) -> list[dict]:
    """이미지에서 얼굴을 검출하고 원본 픽셀 좌표로 반환한다."""

    path = Path(image_path).resolve()

    if not path.is_file():
        raise FileNotFoundError(f"이미지를 찾을 수 없습니다: {path}")

    if not MODEL_PATH.is_file():
        raise FileNotFoundError(f"얼굴 검출 모델이 없습니다: {MODEL_PATH}")

    # 확장자와 실제 파일 형식이 달라도 Pillow로 읽는다.
    with Image.open(path) as image:
        rgb = np.asarray(image.convert("RGB"), dtype=np.uint8).copy()

    height, width = rgb.shape[:2]
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)

    # YuNet 얼굴 검출기
    detector = cv2.FaceDetectorYN.create(
        str(MODEL_PATH),
        "",
        (width, height),
        MIN_CONF,
        0.3,
        5000,
    )

    _, detections = detector.detect(bgr)

    if detections is None:
        return []

    faces = []

    for detection in detections:
        # YuNet: x, y, bbox너비, bbox높이, ..., 신뢰도
        x, y, w, h = map(float, detection[:4])
        conf = float(detection[14])

        if not math.isfinite(conf) or conf < MIN_CONF:
            continue

        # 원본 이미지의 정수 픽셀 좌표로 변환
        x1 = max(0, min(width, math.floor(x)))
        y1 = max(0, min(height, math.floor(y)))
        x2 = max(0, min(width, math.ceil(x + w)))
        y2 = max(0, min(height, math.ceil(y + h)))

        if x1 >= x2 or y1 >= y2:
            continue

        faces.append({
            "bbox": [x1, y1, x2, y2],
            "conf": round(conf, 4),
        })

    # 위에서 아래로, 같은 높이면 왼쪽부터 정렬
    faces.sort(
        key=lambda face: (
            face["bbox"][1],
            face["bbox"][0],
        )
    )

    return faces