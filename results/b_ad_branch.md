# W6 광고성 검색 분기

## 목적

광고성 여부를 RAG 검색 범위에 반영하여 비광고 글에 광고 정책이 불필요하게 근거로 제시되는 문제를 줄이고, 광고성 글에서는 광고·홍보 정책도 함께 검색되도록 수정했다.

## 수정 내용

- `llm/explain.py`의 검색 기준을 `purpose` 대신 `ad_detected` 중심으로 변경
- 광고성 감지 시: `purpose="ad"` → 광고·홍보 + 전체 정책
- 비광고 + `ad_rule` finding: `purpose=None` → 필터 없이 검색
- 비광고 + 일반 finding: `purpose="none"` → 전체 정책만 검색
- `eval/a_test_explain.py`도 새 인터페이스에 맞게 수정
- `pipeline.py`에서 `check_ad()` 결과의 `ad_signal.detected`를 `explain_findings()`에 전달

## Before / After

| 케이스 | ad_detected | 수정 전 Top3 | 수정 후 Top3 |
|---|---:|---|---|
| 비광고 혐오 | False | META-ADS-01, YT-CG-01, KCC-COMM-08 | YT-CG-01, KCC-COMM-08, NISA-44-7 |
| 규칙 감지 광고성 혐오 | True | META-ADS-01, YT-CG-01, KCC-COMM-08 | META-ADS-01, YT-CG-01, KCC-COMM-08 |
| 비광고 + 과대광고 finding | False | KFTC-ADACT-03-1, GOOG-ADS-01, KFTC-SUBST-01 | KFTC-ADACT-03-1, GOOG-ADS-01, KFTC-SUBST-01 |
| 비광고 개인정보 | False | PIPA-15-1, NISA-44-7 | PIPA-15-1, NISA-44-7 |
| 비광고 정치 | False | YT-CG-01, META-ADS-01, ELECTION-82-8 | YT-CG-01, ELECTION-82-8 |

## 자동 점검

- PASS: 비광고 혐오에서 Meta/Google 광고 정책 제외
- PASS: 광고성 혐오에서 광고 정책 검색 가능
- PASS: 비광고 과대광고 finding에서 KFTC-ADACT-03-1 유지
- PASS: 개인정보 finding 근거 존재
- PASS: 정치 finding 근거 존재

## 결과

광고성 여부에 따라 정책 검색 범위가 의도대로 분기되는 것을 확인했다. 비광고 혐오 표현에서는 광고 정책이 제외되고, 광고성으로 감지된 경우에는 광고 정책이 검색 후보에 포함될 수 있다. 또한 과대광고, 개인정보, 정치 finding은 필요한 근거가 사라지지 않았다.

※ 본 결과는 RAG 검색 분기 동작 확인이며, LLM 설명 품질이나 전체 서비스 정확도를 의미하지 않는다.
