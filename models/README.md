# models/ — 위반 유형 분류 모델

K-MHaS(뉴스 댓글, 9개 라벨 다중 분류)로 `beomi/KcELECTRA-base`를 파인튜닝한 분류기와 예측 함수.
W5부터 이 폴더는 **B 담당** (A는 수정하지 않음).

## 파일

| 파일 | 역할 |
| --- | --- |
| `train_classifier.ipynb` | 학습 노트북 원본 틀. 새 실험은 `notebooks/{a\|b}_train_v{번호}.ipynb`로 복사해서 돌림 |
| `metrics.py` | `evaluate(y_true, y_prob, threshold=0.5)` → micro·macro·라벨별 F1. 모든 결과표에 이 함수 사용 |
| `predict.py` | `predict(text) -> list[finding]` — 출력 JSON v0.2 `findings` 모양으로 반환 |

데이터·라벨 정의는 `data/kmhas.py` (`load_kmhas()`, `LABEL_NAMES`, `LABEL_KO`, `LABEL_MAP`).

## 서버에서 실행하기

모든 작업은 VS Code 왼쪽 아래가 `SSH: ss-team17`인지 확인한 뒤 서버 터미널에서 합니다.

```bash
cd ~/project
source ~/project/.venv/bin/activate      # uv 가상환경 (Python 3.11)
nvidia-smi                               # GPU 비었는지 확인 + 카톡에 "GPU 씀, 몇 시까지"
```

- 패키지 추가는 `uv pip install 이름` → `requirements.txt`에도 한 줄 추가 (`pip install` 직접 금지)
- `datasets==2.19.2` 고정 (4.x 이상은 K-MHaS 로딩 불가)
- 노트북으로 돌릴 때는 오른쪽 위 **Select Kernel → `.venv`** (`~/project/.venv/bin/python`). 시스템 Python 3.12는 선택하지 않음

### 오래 걸리는 학습: screen 안에서

노트북을 `.py`로 바꿔 실행하면 VS Code를 닫거나 노트북이 잠들어도 계속 돕니다.

```bash
screen -S train                                   # 세션 만들기
source ~/project/.venv/bin/activate
python notebooks/b_train_v2.py 2>&1 | tee -a results/b_train_v2.log
# Ctrl+A 누른 다음 D → 빠져나오기 (학습은 계속 돎)
screen -r train                                   # 다시 들어가기
exit                                              # 끝나면 세션 종료 (방치 금지)
```

`nohup … &`, 자동 재시작 스크립트는 학과 정책상 금지.

### 예측 함수 확인

```bash
python -m eval.a_test_predict     # validation 10문장 → v0.2 모양 검사, 마지막에 OK
```

```python
from models.predict import predict
predict("문장1. 문장2")            # 문제 없으면 []
```

## 설정값

학습 노트북 맨 위 **설정 셀**의 값. 실제로 쓴 값은 각 체크포인트의 `train_config.json`에 저장됨.

| 설정 | v1 값 | 의미 |
| --- | --- | --- |
| `MODEL_NAME` | `beomi/KcELECTRA-base` | 사전학습 모델 |
| `MAX_LENGTH` | 64 | 문장 최대 토큰 수. 토큰 길이 95% 지점 37을 32의 배수로 올림. 넘는 부분은 잘림 |
| `BATCH_SIZE` | 32 | 한 번에 학습하는 문장 수 |
| `LR` | 2e-5 | 학습률 |
| `EPOCHS` | 3 | 전체 데이터 반복 횟수 (v0은 1) |
| `SEED` | 42 | 재현용 난수 고정 |
| `SAMPLE_SIZE` | `None` | `None` = 전체 train 78,305건. 숫자를 넣으면 그만큼만 샘플링 (v0은 1000) |
| `SAVE_DIR` | `checkpoints/v1` | 저장 위치. **새 버전마다 번호를 바꿀 것** (안 바꾸면 덮어씀) |
| threshold | 0.5 | sigmoid 확률이 이 값 이상이면 해당 라벨로 판단. `evaluate()`·`predict()` 공통. W6 임계값 실험에서 조정 |

`predict.py`의 경로·기본값: `CKPT_DIR`(쓸 체크포인트), `DEFAULT_THRESHOLD`, `DEFAULT_MAX_LENGTH`.
`train_config.json`에 `threshold`·`max_length`가 있으면 그 값을 우선 사용.

## predict() 출력 규칙 (v0.2)

| K-MHaS 라벨 | category / subtype | hate_target | 판정 |
| --- | --- | --- | --- |
| 출신·외모·연령·성별·종교·인종 | `harmful` / `hate` | `origin` / `physical` / `age` / `gender` / `religion` / `race` | 위반 |
| 욕설 | `harmful` / `profanity` | — | 위반 |
| 정치 | `sensitive` / `political` | — | 검토 필요 (`review_question` 채움) |
| 해당없음 | finding 만들지 않음 | | |

- 문장 단위(`. ! ? … 줄바꿈`)로 나눠 분류. 라벨 하나 = finding 하나 (성별+연령이면 `hate` 2개)
- `location.span` = 그 문장의 시작·끝 (분류기는 단어 위치를 못 짚음)
- `confidence` = sigmoid 확률, `risk` = 위반 `60+40×conf` / 검토 필요 `20+40×conf`
- `source: "classifier"`, `evidence: []`, `message: ""` → RAG·LLM 단계가 채움
- 알려진 한계: 소수점(예: `3.5%`)에서도 문장이 나뉨, 64토큰 넘는 문장은 뒷부분이 잘림

## 결과 파일 위치

| 무엇 | 위치 |
| --- | --- |
| 체크포인트 | `~/project/checkpoints/v{번호}/final/` (GitHub에 안 올림, `.gitignore` 확인) |
| validation 점수 | `checkpoints/v{번호}/final/val_result.json` (micro·macro·라벨별 F1) |
| 학습 설정 | `checkpoints/v{번호}/final/train_config.json` |
| 학습 노트북 | `notebooks/{a\|b}_train_v{번호}.ipynb` |
| 결과 정리 | `results/*.md` + 노션 결과물 모음 페이지 **모델 기록** 표 |

`final/`의 `model.safetensors`(약 440MB), `config.json`, `tokenizer*.json`, `training_args.bin`은 프로그램이 읽는 파일.

## 버전 기록

| 버전 | 바뀐 설정 | val macro F1 |
| --- | --- | --- |
| v0 | 1,000건 샘플, 1 epoch | 0.0793 |
| v1 | 전체 데이터, 3 epoch | 0.7527 |
| v2 | KLUE-RoBERTa | 0.7257 |
| v3 | KcELECTRA + class weight (비율 그대로) | 0.7530 |
| v4 | KLUE-RoBERTa + class weight | 0.7254 |
| **v5** ⭐ | KcELECTRA + **제곱근** class weight, 5 epoch → **현재 사용** | **0.8066** |
| v6 / v7 | 제곱근 weight, 3 / 8 epoch | 0.7934 / 0.8071 |

자세한 비교는 `results/b_model_compare.md`. v7은 v5와 차이가 없어 더 단순한 v5를 채택.

### 지금 쓰는 판정 기준 (`predict.py`)

- 체크포인트: `checkpoints/v5/final`
- 혐오·욕설: 확률 0.4 미만 → finding 없음 / 0.4–0.8 → 검토 필요 / 0.8 이상 → 위반
- 정치: 0.4 이상 → 검토 필요 (위반으로 올리지 않음)
- 근거: `results/b_threshold.md` (validation 그리드 탐색)

## 규칙

- 공식 **test는 W9 최종 평가 때 한 번만**. 점수 확인·체크포인트 선택·임계값 조정은 전부 validation으로
- 실행 중 커널 재시작 금지 (변수가 사라짐, 저장된 파일은 남음)
- Kanana Safeguard·오픈 LLM(약 16GB)과 분류기 학습(약 4–6GB)은 GPU에 같이 올리지 않음
