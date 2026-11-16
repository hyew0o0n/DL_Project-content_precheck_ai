# W6 판정 임계값 실험

## 목적

W5에서 채택한 v3(KcELECTRA + class weight) 모델의 sigmoid 확률을 이용해
텍스트 MVP에서 사용할 `통과 / 검토 필요 / 위반` 판정 경계값을 validation set으로 결정했다.

공식 test set은 사용하지 않았다.

## 평가 설정

- 모델: v3 KcELECTRA + class weight
- checkpoint: `checkpoints/v3/final`
- 데이터: K-MHaS validation 8,776건
- MAX_LENGTH: 64
- 평가 대상
  - 혐오/욕설 7개 라벨: origin, physical, profanity, age, gender, race, religion
  - politics는 별도 검토
  - not_hate는 finding 생성 대상이 아니므로 제외
- threshold 탐색: 0.1 단위
- validation 추론은 1회 수행한 뒤 저장된 sigmoid 확률로 threshold 조합을 비교했다.

## 대표 결과

| 검토 시작 | 위반 시작 | 위반 정밀도 | 위반 Recall | 검토 구간 비율 | Miss 비율 | Harmful Macro F1 | 정치 Precision | 정치 Recall |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0.2 | 0.8 | 0.7799 | 0.8933 | 0.0287 | 0.0529 | 0.6534 | 0.6148 | 0.9621 |
| 0.3 | 0.8 | 0.7799 | 0.8933 | 0.0202 | 0.0620 | 0.6859 | 0.6602 | 0.9542 |
| **0.4** | **0.8** | **0.7799** | **0.8933** | **0.0152** | **0.0710** | **0.7033** | **0.6971** | **0.9453** |
| 0.5 | 0.8 | 0.7799 | 0.8933 | 0.0109 | 0.0792 | 0.7208 | 0.7168 | 0.9408 |
| 0.5 | 0.9 | 0.8149 | 0.8672 | 0.0163 | 0.0792 | 0.7208 | 0.7168 | 0.9408 |

※ 검토 구간 비율은 게시글 비율이 아니라 harmful 7개 라벨의 전체 label-level 판정 중
`review_threshold <= probability < violation_threshold`에 들어간 비율이다.

※ Miss 비율은 실제 harmful positive label 중 `review_threshold`보다 낮아
통과 영역으로 내려간 비율이다.

## 최종 선택

- `review_threshold = 0.4`
- `violation_threshold = 0.8`

### 혐오·욕설

- confidence < 0.4 → 통과
- 0.4 <= confidence < 0.8 → 검토 필요
- confidence >= 0.8 → 위반

### 정치

정치 표현은 프로젝트 기획상 모델 확률만으로 위반을 단정하지 않는다.

- confidence < 0.4 → 통과
- confidence >= 0.4 → 검토 필요

## 선택 이유

`0.5 / 0.8` 조합은 harmful Macro F1과 정치 precision이 더 높았지만,
실제 harmful positive가 통과 영역으로 내려가는 Miss 비율이 0.0792까지 증가했다.

반대로 `0.3 / 0.8`은 Miss 비율을 0.0620까지 줄일 수 있지만,
검토 구간이 넓어지고 정치 precision이 0.6602까지 낮아진다.

`0.4 / 0.8`은 위반 정밀도 0.7799와 위반 Recall 0.8933을 유지하면서,
Miss 비율 0.0710, 정치 Recall 0.9453으로
과도하게 많은 항목을 검토 대상으로 보내지 않으면서도 위험 표현을 놓치지 않는 방향의 절충안이다.

본 서비스는 AI가 최종 위반 여부를 확정하는 시스템이 아니라
위험 가능성이 있는 콘텐츠를 사전에 탐지하고 애매한 경우 사람 검토로 넘기는 보조 시스템이므로
precision만 최대화하기보다 Miss를 줄이는 방향도 함께 고려했다.

## 생성 파일

- `results/b_threshold_probs.npz`: validation 정답 및 sigmoid 확률
- `results/b_threshold_grid.csv`: threshold 전체 조합 결과
- `results/b_threshold.md`: 최종 분석 및 선택 결과

※ 본 threshold는 K-MHaS validation set 기준으로 결정한 값이며,
공식 test 성능이나 실제 서비스 환경 전체의 정확도를 의미하지 않는다.
