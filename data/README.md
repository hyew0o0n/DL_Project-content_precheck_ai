# data/

| 파일 | 내용 |
| --- | --- |
| `kmhas.py` | K-MHaS 로더 + 라벨 정의 (`load_kmhas()`, `LABEL_NAMES`, `LABEL_KO`, `LABEL_MAP`). 학습·평가·데모 코드가 모두 import |
| `b_normal_ads.csv` | 정상 광고 문구 (과대광고 오탐률 측정용, 업종별) |
| `images/I1–I8.png` | 데모·동작 확인용 이미지 (노션 **데모·평가용 예시 모음** 페이지에 이미지별 설명) |
| `images/b_ocr_test/` | OCR 모델 비교(EasyOCR vs PaddleOCR)에 쓴 I5·I6 원본 |

- K-MHaS는 파일로 두지 않고 HuggingFace에서 바로 받습니다 ([원본](https://github.com/adlnlp/K-MHaS), CC-BY-SA-4.0). `datasets==2.19.2` 고정 (4.x 이상은 로딩 불가)
- 정리 후 건수: train 78,305 / val 8,776 / test 21,939 (빈 문장 0, 중복 421, test와 겹침 251 제거)
- 영상 배경 원본(`video_bg/`)은 Pexels 영상이라 저장소에 올리지 않습니다 → 서버 `~/project/data/video_bg/`
