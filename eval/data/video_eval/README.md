# W8 합성 영상 평가셋 v1

## 구성

- `videos/V01.mp4`~`V10.mp4`: 각 10초, 720×1280, 15fps, 무음 H.264 (**저장소에 없음**, 서버에만 있음 → 없으면 아래 '재생성')
- `captions/V01.png`~`V10.png`: 합성에 사용한 투명 배경 한글 자막
- `labels.json`: 영상별 자막, 문제 유형, 노출 시작/종료 시각, 이론상 1fps 관측 여부
- `background_sources.csv`: 원본 배경 영상 출처와 라이선스 기록용 시트(미기입 상태는 **검증 전**)
- `eval/video_eval/make_video_set.py`: 재생성 스크립트
- `eval/video_eval/validate_video_set.py`: 구조 검증 스크립트
- `data/video_bg/bg01.mp4`~`bg05.mp4`: 원본 배경 영상 (Pexels, 저장소에 없음, 서버에만 있음)
- `ocr_eval_all.csv` · `ocr_eval_all_summary.json`: 실제 PaddleOCR 평가 결과
- `video_text_eval.json` · `video_text_eval_summary.json`: OCR 결과로 분류기·규칙을 돌린 결과

## 빠른 확인

프로젝트 최상위 폴더에서 실행:

```bash
python eval/video_eval/validate_video_set.py
```

이 검사는 영상 수·파일 형식·길이·라벨 구조를 확인할 뿐, 딥러닝 모델이나 Gemini는 호출하지 않습니다.

## 재생성

한글 폰트(PIL `ImageFont`에서 사용 가능), Pillow, `ffmpeg`, `ffprobe`가 필요합니다. MoviePy는 필요 없습니다. 서버의 기존 `eval/video_eval/render_text.py`를 그대로 사용합니다.

```bash
python eval/video_eval/make_video_set.py --resume
```

- `--resume`: 완성된 영상은 건너뛰고 나머지 영상 생성
- `--overwrite`: 기존 생성 결과를 모두 다시 작성 (평가 결과가 고정된 후엔 주의)

## 라벨과 평가상의 주의

- `label=issue`는 합성 시 지정한 **수동 문제 사례 후보**, `label=normal`은 **수동 정상 후보**입니다. 해당 영상의 법적 위반 또는 모델 검출 성공이 자동으로 입증되는 것은 아닙니다.
- 오디오 및 자막 이외 영상 내용(표지판, 배경 텍스트, 얼굴 등)도 실제 모델 출력에 영향을 줄 수 있습니다.
- `ideal_1fps_sample_times_sec`는 정수 초 0~9초를 샘플링한다고 가정한 이론적 관측 시점입니다. 실제 추출 위상·타임스탬프는 별도 확인해야 합니다.
- 실제 FFmpeg 1fps 추출 프레임은 표시된 정수 초보다 약 0.5초 뒤 화면입니다 (`fix_sampling_alignment.py`로 라벨 보정, mp4는 그대로). 보정 후 **V01(0.5초 노출)은 샘플에 잡히고 V02(0.5초 노출)는 놓칩니다.**
- 이 결과를 보고 영상 얼굴 필터(24px)를 정했으므로, 이 10개의 수치는 **개발용 예비 수치**입니다. W9 최종 평가는 문구·배경을 바꾼 새 합성셋으로 하는 것을 권장합니다.
- 모델 오탐·미탐, OCR 검출률, 영상 문제 구간 병합 정확도는 별도로 평가해야 합니다. 이 10개는 **소규모 합성 기능검증셋**이며 일반화 성능을 대표하지 않습니다.
- 원본 영상의 Pexels 등 다운로드 URL과 이용허락 조건을 사용자가 직접 기록해야 합니다. 원본 및 합성 영상을 재배포하기 전 해당 이용 조건을 확인하세요.
- 문제 사례의 전화번호는 가상 예시로만 사용했고 실제 개인 연락처를 수집하지 않았습니다.
