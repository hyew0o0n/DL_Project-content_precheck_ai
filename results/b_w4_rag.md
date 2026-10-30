# W4 RAG 결과

## 1. Policy KB

- Google Sheet 기반 정책 KB 생성
- `rag/build_kb.py` 구현
- `rag/policy_kb.jsonl` 생성
- 전체 정책: 18개
- doc_id 누락: 0
- doc_id 중복: 0
- 짧은 정책 본문 보강 완료

## 2. RAG 환경

- Embedding model: BAAI/bge-m3
- Vector DB: Chroma
- HF cache: `/nfs/team/hf_cache`
- Vector DB: `/nfs/team/vectordb`
- GPU: NVIDIA RTX A5000
- `embed_text`만 임베딩하고 나머지 정책 정보는 metadata로 저장

## 3. 검색 테스트

### 1) 협찬/광고 표시 누락
- Filter ON 1위: `KFTC-ENDORSE-06-1`
- score: 0.4831

### 2) 특정 집단 혐오 표현
- `META-ADS-01`: 0.5720
- `KCC-COMM-08`: 0.5664
- `YT-CG-01`: 0.5130

### 3) 개인정보 노출
- Filter ON:
  - `PIPA-15-1`: 0.6433
  - `NISA-44-7`: 0.5031
- Filter OFF에 포함됐던 초상권 정책이 Filter ON에서 제거됨

### 4) 선거 관련 딥페이크
- Filter ON 1위: `ELECTION-82-8`
- score: 0.6364

### 5) 타사 로고·캐릭터 무단 사용
- Filter ON 1위: `IP-LAW-01`
- score: 0.6540

### 필터 OFF/ON 비교 요약

| 질문 | 위반 유형 | 기대 조항 | 필터 OFF | 필터 ON | 결과 |
|---|---|---|---|---|---|
| 협찬 광고 표시 누락 | `missing_disclosure` | `KFTC-ENDORSE-06-1` | 1위 | 1위 | ✅ |
| 특정 집단 혐오 표현 | `hate` | 혐오 관련 정책 | Meta 1위, KCC 2위, YouTube 3위 | 동일 | ✅ 관련 정책 유지 |
| 개인정보 노출 | `phone`, `rrn`, `account` | `PIPA-15-1` | 1위 | 1위 | ✅ 초상권 정책 제거 |
| 선거 관련 딥페이크 | `political` | `ELECTION-82-8` | 1위 | 1위 | ✅ 정치 관련 정책으로 제한 |
| 타사 로고·캐릭터 무단 사용 | `ip` | `IP-LAW-01` | 1위 | 1위 | ✅ 관련 없는 정책 제거 |

## 4. 결과

- BGE-M3 기반 정책 검색 정상 동작
- Chroma Vector DB 18개 문서 저장 확인
- `violation_types` 필터 정상 동작
- `purpose` 필터 정상 동작
- 대표 테스트인 협찬 표시 누락 검색에서 `KFTC-ENDORSE-06-1`이 1순위로 검색됨
