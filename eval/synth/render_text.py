
"""한글 문구 PNG 생성 (투명 배경 + 반투명 띠 + 흰 글씨).

W8에 영상 합성 평가셋용으로 만들었고, 영상 제외 후에는 이미지 합성 평가셋(개인정보·광고 문구를
배경 이미지 위에 얹기)에 재사용한다.
"""

import argparse
import subprocess
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def find_korean_font():
    """서버에 설치된 한글 폰트 경로를 찾는다."""
    result = subprocess.run(
        [
            "fc-list",
            ":lang=ko",
            "-f",
            "%{file}\n",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    for line in result.stdout.splitlines():
        path = Path(line.strip())

        if path.is_file():
            return str(path)

    raise RuntimeError(
        "한글 폰트를 찾지 못했습니다. "
        "서버의 한글 폰트 설치 상태를 확인하세요."
    )


def render_text(
    text: str,
    output_path: str,
    width: int = 720,
    height: int = 1280,
    font_size: int = 52,
):
    """투명한 배경 위에 한글 자막을 그린다."""
    if not text.strip():
        raise ValueError("자막 내용이 비어 있습니다.")

    font_path = find_korean_font()
    font = ImageFont.truetype(
        font_path,
        font_size,
    )

    image = Image.new(
        "RGBA",
        (width, height),
        (0, 0, 0, 0),
    )

    draw = ImageDraw.Draw(image)

    # 긴 자막은 여러 줄로 나눈다.
    wrapped = "\n".join(
        textwrap.wrap(
            text,
            width=16,
            break_long_words=True,
            break_on_hyphens=False,
        )
    )

    spacing = 12
    stroke_width = 2

    bbox = draw.multiline_textbbox(
        (0, 0),
        wrapped,
        font=font,
        spacing=spacing,
        align="center",
        stroke_width=stroke_width,
    )

    left, top, right, bottom = bbox
    text_width = right - left
    text_height = bottom - top

    # 영상 하단 부근에 자막 배치
    center_x = width / 2
    center_y = height * 0.72

    x = center_x - text_width / 2 - left
    y = center_y - text_height / 2 - top

    padding_x = 30
    padding_y = 22

    background_box = [
        x + left - padding_x,
        y + top - padding_y,
        x + right + padding_x,
        y + bottom + padding_y,
    ]

    # 검은색 반투명 자막 배경
    draw.rounded_rectangle(
        background_box,
        radius=18,
        fill=(0, 0, 0, 190),
    )

    # 흰색 한글 자막
    draw.multiline_text(
        (x, y),
        wrapped,
        font=font,
        fill=(255, 255, 255, 255),
        spacing=spacing,
        align="center",
        stroke_width=stroke_width,
        stroke_fill=(0, 0, 0, 255),
    )

    output = Path(output_path)
    output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    image.save(output)

    return str(output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--text",
        required=True,
    )

    parser.add_argument(
        "--output",
        required=True,
    )

    parser.add_argument(
        "--width",
        type=int,
        default=720,
    )

    parser.add_argument(
        "--height",
        type=int,
        default=1280,
    )

    args = parser.parse_args()

    result = render_text(
        text=args.text,
        output_path=args.output,
        width=args.width,
        height=args.height,
    )

    print("✅ 자막 이미지 생성 완료")
    print("저장 위치:", result)
