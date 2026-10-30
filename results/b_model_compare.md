# W5 분류기 비교 실험

## 실험 기준

- 데이터: K-MHaS
- Train: 78,305 / Validation: 8,776
- 비교 기준: validation macro F1 + 라벨별 F1
- 공식 test split은 사용하지 않음
- 공통 설정: MAX_LENGTH 64 / batch 32 / lr 2e-5 / epoch 3 / threshold 0.5

## 모델 비교

| 버전 | 모델 | Class Weight | Micro F1 | Macro F1 |
|---|---|---:|---:|---:|
| v1 | KcELECTRA | X | 0.8839 | 0.7527 |
| v2 | KLUE-RoBERTa | X | 0.8534 | 0.7257 |
| v3 | KcELECTRA | O | 0.8540 | 0.7530 |
| v4 | KLUE-RoBERTa | O | 0.8219 | 0.7254 |

## 라벨별 F1

| 라벨 | v1 | v2 | v3 | v4 |
|---|---:|---:|---:|---:|
| origin | 0.8102 | 0.7848 | 0.7607 | 0.7581 |
| physical | 0.8330 | 0.7943 | 0.7912 | 0.7418 |
| politics | 0.8529 | 0.8320 | 0.8137 | 0.7882 |
| profanity | 0.9288 | 0.8500 | 0.9084 | 0.8091 |
| age | 0.8317 | 0.8097 | 0.8088 | 0.7463 |
| gender | 0.7617 | 0.7428 | 0.7012 | 0.6944 |
| race | 0.0000 | 0.0000 | 0.3368 | 0.3168 |
| religion | 0.8333 | 0.8185 | 0.7389 | 0.7751 |
| not_hate | 0.9227 | 0.8997 | 0.9172 | 0.8987 |

## 채택 모델

- **v3: KcELECTRA + class weight O**
- Validation macro F1: **0.7530**
- race F1: v1 0.0000 → v3 0.3368
- 해석: class weight 적용으로 희소 라벨 race의 F1이 개선되었고 macro F1은 baseline과 거의 비슷한 수준에서 소폭 상승했다. 다만 일부 다른 라벨의 F1은 감소했다.
