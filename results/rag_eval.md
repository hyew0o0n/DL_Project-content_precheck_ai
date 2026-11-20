# RAG 검색 평가 (Recall@3, filter OFF)

- 질문: 25개 (W5 20개 + W8 권리 5개)
- Hit: **24/25**  /  Recall@3: **0.9600**

| # | 질문 | 정답 doc_id (하나라도 맞으면 Hit) | Top 3 | Hit |
|---|---|---|---|:---:|
| Q01 | AI를 이용한 서비스인데 이용 전에 인공지능을 사용한다는 사실을 사용자에게 알리지 않았다. | AI-LAW-31-1 | AI-LAW-31-1<br>AI-LAW-31-3<br>AI-LAW-31-2 | O |
| Q02 | AI로 생성한 이미지와 글을 게시하면서 인공지능이 생성한 결과물이라는 표시를 하지 않았다. | AI-LAW-31-2 | AI-LAW-31-2<br>KFTC-ENDORSE-05-1<br>KFTC-SUBST-01 | O |
| Q03 | 실제 사람처럼 보이는 AI 가상인물이 등장하는 콘텐츠인데 가상 인물이라는 사실을 명확하게 고지하지 않았다. | AI-LAW-31-3 | KFTC-ENDORSE-05-1<br>AI-LAW-31-3<br>YT-PRIV-01 | O |
| Q04 | AI 생성 결과물의 고지나 표시 의무에서 제외되는 예외와 구체적인 기준을 확인하고 싶다. | AI-LAW-31-4 | AI-LAW-31-4<br>AI-LAW-31-3<br>KFTC-SUBST-01 | O |
| Q05 | 건강식품을 광고하면서 이 제품을 먹으면 질병이 완치된다고 홍보했다. | KFTC-FOOD-08-1 | KFTC-FOOD-08-1<br>KFTC-ENDORSE-06-1<br>KFTC-ADACT-03-1 | O |
| Q06 | AI로 만든 가상인물이 제품을 추천하는 광고에 등장했다. 가상인물 광고 표시 기준을 확인하고 싶다. | KFTC-ENDORSE-05-1 | KFTC-ENDORSE-05-1<br>AI-LAW-31-3<br>GOOG-ADS-01 | O |
| Q07 | 제품을 무료로 제공받아 후기를 작성했지만 광고나 협찬이라는 표시를 하지 않았다. | KFTC-ENDORSE-06-1 | KFTC-ENDORSE-06-1<br>KFTC-ENDORSE-05-1<br>KFTC-SUBST-01 | O |
| Q08 | 상품 광고에 아무 근거 없이 100% 효과, 무조건 성공 같은 과장된 표현을 사용했다. | KFTC-ADACT-03-1 | KFTC-SUBST-01<br>KFTC-FOOD-08-1<br>KFTC-ADACT-03-1 | O |
| Q09 | 선거운동을 위해 후보자의 얼굴과 음성을 합성한 딥페이크 영상을 제작해 게시했다. | ELECTION-82-8 | ELECTION-82-8<br>KFTC-ENDORSE-05-1<br>YT-CG-01 | O |
| Q10 | 정보통신망을 통해 불법 정보나 타인을 비방하는 내용을 온라인에 유통하는 경우의 금지 기준을 확인하고 싶다. | NISA-44-7 | NISA-44-7<br>KCC-COMM-08<br>META-ADS-01 | O |
| Q11 | 온라인 게시물에서 특정 집단을 차별하거나 비하하는 표현을 사용했다. 정보통신 심의 기준을 확인하고 싶다. | KCC-COMM-08 | KCC-COMM-08<br>META-ADS-01<br>NISA-44-7 | O |
| Q12 | Meta 광고에 특정 집단을 차별하고 혐오하는 표현이 포함되어 있다. | META-ADS-01 | META-ADS-01<br>META-IP-01<br>GOOG-ADS-01 | O |
| Q13 | Google Ads 광고에 신뢰하기 어려운 과장 표현과 부적절한 콘텐츠가 포함되어 있다. | GOOG-ADS-01 | GOOG-ADS-01<br>META-ADS-01<br>KFTC-ADACT-03-1 | O |
| Q14 | YouTube 영상에 혐오 표현과 정치적으로 민감한 표현이 포함되어 있다. 커뮤니티 가이드라인을 확인하고 싶다. | YT-CG-01 | YT-CG-01<br>YT-PRIV-01<br>META-ADS-01 | O |
| Q15 | 광고에서 국내 최초, 100% 효과라고 단정했지만 이를 입증할 실증 자료가 없다. | KFTC-SUBST-01 | KFTC-SUBST-01<br>KFTC-FOOD-08-1<br>KFTC-ENDORSE-05-1 | O |
| Q16 | 게시물에 다른 사람의 전화번호, 주민등록번호와 계좌번호를 동의 없이 공개했다. | PIPA-15-1 | PIPA-15-1<br>YT-PRIV-01<br>PORTRAIT-CASE-01 | O |
| Q17 | 다른 회사의 로고, 상표와 캐릭터를 허락 없이 콘텐츠와 광고에 사용했다. | TM-LAW-108, COPYRIGHT-136-1, UCPA-02-1-GA | META-IP-01<br>UCPA-02-1-TA<br>TM-LAW-108 | O |
| Q18 | 다른 사람의 얼굴 사진을 동의 없이 광고에 사용하고 합성했다. | PORTRAIT-CASE-01, CIVIL-750, UCPA-02-1-TA | PORTRAIT-CASE-01<br>YT-PRIV-01<br>UCPA-02-1-TA | O |
| Q19 | 업체에서 원고료를 받고 제품을 추천했지만 경제적 이해관계나 광고 사실을 표시하지 않았다. | KFTC-ENDORSE-06-1 | KFTC-ENDORSE-06-1<br>KFTC-FOOD-08-1<br>KFTC-ENDORSE-05-1 | O |
| Q20 | SNS 게시물에 다른 사람의 휴대전화 번호와 이메일 주소를 그대로 노출했다. | PIPA-15-1 | PIPA-15-1<br>IG-TM-01<br>YT-PRIV-01 | O |
| Q21 | 광고 영상에 유명 스포츠 브랜드 로고를 허락 없이 크게 넣어 우리 제품처럼 보이게 했다. | TM-LAW-108, UCPA-02-1-GA | KFTC-FOOD-08-1<br>META-IP-01<br>KFTC-ADACT-03-1 | X |
| Q22 | 인기 애니메이션 캐릭터 그림을 그대로 가져와 굿즈 홍보 이미지에 사용했다. | COPYRIGHT-136-1 | KFTC-ENDORSE-05-1<br>UCPA-02-1-TA<br>COPYRIGHT-136-1 | O |
| Q23 | 유튜브 영상 썸네일에 다른 회사 상표를 넣어 그 회사와 관련 있는 것처럼 보이게 했다. | YT-TM-01, TM-LAW-108 | YT-TM-01<br>TM-LAW-108<br>YT-PRIV-01 | O |
| Q24 | 연예인 사진을 허락 없이 제품 광고에 넣어 그 연예인이 추천하는 것처럼 보이게 했다. | UCPA-02-1-TA, PORTRAIT-CASE-01 | UCPA-02-1-TA<br>KFTC-ENDORSE-05-1<br>KFTC-FOOD-08-1 | O |
| Q25 | 길에서 찍힌 일반인 얼굴이 알아볼 수 있게 나온 사진을 동의 없이 SNS 홍보 게시물에 올렸다. | PORTRAIT-CASE-01, CIVIL-750 | YT-PRIV-01<br>PORTRAIT-CASE-01<br>UCPA-02-1-TA | O |
