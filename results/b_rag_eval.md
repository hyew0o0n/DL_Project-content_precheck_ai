# W5 RAG 검색 평가

## 평가 조건

- 정책 KB: 18개 문서
- 검색 모델: BGE-M3
- Vector DB: Chroma
- 검색 조건: filter OFF
- 평가 질문: 20개
- 정답 조항은 검색 전에 직접 지정
- 평가 지표: Recall@3

## 결과

- Hit: **20/20**
- Recall@3: **1.0000 (100.0%)**

| # | 질문 | 정답 doc_id | Top 3 | Hit |
|---:|---|---|---|:---:|
| 1 | AI를 이용한 서비스인데 이용 전에 인공지능을 사용한다는 사실을 사용자에게 알리지 않았다. | AI-LAW-31-1 | 1. AI-LAW-31-1<br>2. AI-LAW-31-3<br>3. AI-LAW-31-2 | O |
| 2 | AI로 생성한 이미지와 글을 게시하면서 인공지능이 생성한 결과물이라는 표시를 하지 않았다. | AI-LAW-31-2 | 1. AI-LAW-31-2<br>2. KFTC-ENDORSE-05-1<br>3. KFTC-SUBST-01 | O |
| 3 | 실제 사람처럼 보이는 AI 가상인물이 등장하는 콘텐츠인데 가상 인물이라는 사실을 명확하게 고지하지 않았다. | AI-LAW-31-3 | 1. KFTC-ENDORSE-05-1<br>2. AI-LAW-31-3<br>3. GOOG-ADS-01 | O |
| 4 | AI 생성 결과물의 고지나 표시 의무에서 제외되는 예외와 구체적인 기준을 확인하고 싶다. | AI-LAW-31-4 | 1. AI-LAW-31-4<br>2. AI-LAW-31-3<br>3. KFTC-SUBST-01 | O |
| 5 | 건강식품을 광고하면서 이 제품을 먹으면 질병이 완치된다고 홍보했다. | KFTC-FOOD-08-1 | 1. KFTC-FOOD-08-1<br>2. KFTC-ENDORSE-06-1<br>3. KFTC-ADACT-03-1 | O |
| 6 | AI로 만든 가상인물이 제품을 추천하는 광고에 등장했다. 가상인물 광고 표시 기준을 확인하고 싶다. | KFTC-ENDORSE-05-1 | 1. KFTC-ENDORSE-05-1<br>2. AI-LAW-31-3<br>3. GOOG-ADS-01 | O |
| 7 | 제품을 무료로 제공받아 후기를 작성했지만 광고나 협찬이라는 표시를 하지 않았다. | KFTC-ENDORSE-06-1 | 1. KFTC-ENDORSE-06-1<br>2. KFTC-ENDORSE-05-1<br>3. KFTC-SUBST-01 | O |
| 8 | 상품 광고에 아무 근거 없이 100% 효과, 무조건 성공 같은 과장된 표현을 사용했다. | KFTC-ADACT-03-1 | 1. KFTC-SUBST-01<br>2. KFTC-FOOD-08-1<br>3. KFTC-ADACT-03-1 | O |
| 9 | 선거운동을 위해 후보자의 얼굴과 음성을 합성한 딥페이크 영상을 제작해 게시했다. | ELECTION-82-8 | 1. ELECTION-82-8<br>2. KFTC-ENDORSE-05-1<br>3. YT-CG-01 | O |
| 10 | 정보통신망을 통해 불법 정보나 타인을 비방하는 내용을 온라인에 유통하는 경우의 금지 기준을 확인하고 싶다. | NISA-44-7 | 1. NISA-44-7<br>2. KCC-COMM-08<br>3. META-ADS-01 | O |
| 11 | 온라인 게시물에서 특정 집단을 차별하거나 비하하는 표현을 사용했다. 정보통신 심의 기준을 확인하고 싶다. | KCC-COMM-08 | 1. KCC-COMM-08<br>2. META-ADS-01<br>3. NISA-44-7 | O |
| 12 | Meta 광고에 특정 집단을 차별하고 혐오하는 표현이 포함되어 있다. | META-ADS-01 | 1. META-ADS-01<br>2. GOOG-ADS-01<br>3. KFTC-ADACT-03-1 | O |
| 13 | Google Ads 광고에 신뢰하기 어려운 과장 표현과 부적절한 콘텐츠가 포함되어 있다. | GOOG-ADS-01 | 1. GOOG-ADS-01<br>2. META-ADS-01<br>3. KFTC-ADACT-03-1 | O |
| 14 | YouTube 영상에 혐오 표현과 정치적으로 민감한 표현이 포함되어 있다. 커뮤니티 가이드라인을 확인하고 싶다. | YT-CG-01 | 1. YT-CG-01<br>2. META-ADS-01<br>3. GOOG-ADS-01 | O |
| 15 | 광고에서 국내 최초, 100% 효과라고 단정했지만 이를 입증할 실증 자료가 없다. | KFTC-SUBST-01 | 1. KFTC-SUBST-01<br>2. KFTC-FOOD-08-1<br>3. KFTC-ENDORSE-05-1 | O |
| 16 | 게시물에 다른 사람의 전화번호, 주민등록번호와 계좌번호를 동의 없이 공개했다. | PIPA-15-1 | 1. PIPA-15-1<br>2. PORTRAIT-GUIDE-01<br>3. NISA-44-7 | O |
| 17 | 다른 회사의 로고, 상표와 캐릭터를 허락 없이 콘텐츠와 광고에 사용했다. | IP-LAW-01 | 1. IP-LAW-01<br>2. PORTRAIT-GUIDE-01<br>3. GOOG-ADS-01 | O |
| 18 | 다른 사람의 얼굴 사진을 동의 없이 광고에 사용하고 합성했다. | PORTRAIT-GUIDE-01 | 1. PORTRAIT-GUIDE-01<br>2. IP-LAW-01<br>3. KFTC-ENDORSE-05-1 | O |
| 19 | 업체에서 원고료를 받고 제품을 추천했지만 경제적 이해관계나 광고 사실을 표시하지 않았다. | KFTC-ENDORSE-06-1 | 1. KFTC-ENDORSE-06-1<br>2. KFTC-FOOD-08-1<br>3. KFTC-ENDORSE-05-1 | O |
| 20 | SNS 게시물에 다른 사람의 휴대전화 번호와 이메일 주소를 그대로 노출했다. | PIPA-15-1 | 1. PIPA-15-1<br>2. PORTRAIT-GUIDE-01<br>3. NISA-44-7 | O |

## 해석

- 20개 검증 질문 중 20개 모두 정답 조항이 상위 3개 안에 포함되었다.
- 따라서 본 검증 세트 기준 Recall@3는 100%이다.
- 본 결과는 직접 구성한 20개 검색 확인용 질문에 대한 결과이며, 일반적인 모든 질의에서 100% 성능을 의미하지는 않는다.
