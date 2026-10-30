"""rules/ad_patterns.py 동작 확인 (W5)

실행: python -m eval.a_test_ad_patterns
- 예시 글마다 기대값(광고성 감지 / 표시 누락 / 과대광고 판정)과 실제 결과를 비교
- 마지막 줄에 "OK: n/n" 이 나오면 통과. 틀린 예시는 FAIL로 표시됨
- 숫자 검증(오탐률·탐지율)이 아니라 데모용 확인. 숫자 검증은 W9 (기획안 5-4)
"""

import json

from rules.ad_patterns import check_ad

# (글, purpose, 기대: 광고성 감지?, 기대: 표시 누락 판정, 기대: 과대광고 판정 목록)
CASES = [
    # ── 광고인데 표시 없음 ──
    ("이 크림 하나면 주름 100% 개선! 프로필 링크에서 쿠폰코드 SALE10 입력하세요",
     "none", True, "검토 필요", ["위반"]),
    ("공구 오픈했어요~ 이번 주까지만 20% 할인! 링크는 프로필에 있어요",
     "none", True, "검토 필요", []),
    ("강추! 진짜 인생템이에요 다들 써보세요",                   # 약한 신호 2개 → 감지
     "none", True, "검토 필요", []),
    ("먹기만 해도 -10kg! 부작용 없는 다이어트",                  # 목적=광고 → 표시 누락 위반
     "ad", True, "위반", ["위반", "위반", "위반"]),
    # ── 광고인데 표시 있음 → 표시 누락 없음 ──
    ("#광고 이번 신상 립스틱 20% 할인 중! 구매 링크는 프로필에",
     "none", True, None, []),
    ("업체로부터 제품을 제공받아 작성한 솔직 후기입니다. 할인코드 HAPPY 쓰세요",
     "none", True, None, []),
    ("[광고] 국내 최초 AI 기반 피부 진단 앱",
     "none", False, None, ["검토 필요", "검토 필요"]),
    # ── 일반 글 → 아무것도 안 걸려야 함 (오탐 확인) ──
    ("이 영화 강추",                                            # 약한 신호 1개 → 감지 X
     "none", False, None, []),
    ("친구한테 추천해요 분위기 좋은 카페",
     "none", False, None, []),
    ("오늘 날씨 진짜 좋다 산책 다녀옴",
     "daily", False, None, []),
    ("이 티셔츠 100% 면이라 촉감 좋아요",                        # exclude로 걸러져야 함
     "none", False, None, []),
    ("시험 100% 망했다 ㅠㅠ",                                    # 알려진 한계: 걸림 (아래 참고)
     "none", False, None, ["검토 필요"]),
    # ── 과대광고만 ──
    ("의사가 추천하는 탈모 치료 샴푸, 효과 보장",
     "none", False, None, ["검토 필요", "위반", "검토 필요"]),  # 글에 나온 순서대로
]


def summarize(out):
    fs = out["findings"]
    disc = next((f["verdict"] for f in fs if f["subtype"] == "missing_disclosure"), None)
    exag = [f["verdict"] for f in fs if f["subtype"] == "exaggeration"]
    return out["ad_signal"]["detected"], disc, exag


def main():
    ok = 0
    for i, (text, purpose, exp_det, exp_disc, exp_exag) in enumerate(CASES):
        out = check_ad(text, purpose)
        got = summarize(out)
        passed = got == (exp_det, exp_disc, exp_exag)
        ok += passed
        mark = "ok  " if passed else "FAIL"
        sig = ", ".join(f"{s['text']}({s['weight']})" for s in out["debug"]["signals"]) or "-"
        exag = ", ".join(f"{f['location']['text']}→{f['verdict']}"
                         for f in out["findings"] if f["subtype"] == "exaggeration") or "-"
        print(f"[{i:2}] {mark} {text}")
        print(f"      광고성 {out['ad_signal']['score']:.2f} ({out['ad_signal']['by']}) | 신호: {sig}")
        print(f"      표시 {'있음' if out['ad_signal']['disclosure_found'] else '없음'} | "
              f"표시 누락: {got[1] or '-'} | 과대광고: {exag}")
        if not passed:
            print(f"      기대: {(exp_det, exp_disc, exp_exag)}  실제: {got}")

    print("\n예시 [0] 전체 출력 (v0.2 모양)")
    out = check_ad(CASES[0][0], "none")
    print(json.dumps({"ad_signal": out["ad_signal"], "findings": out["findings"]},
                     ensure_ascii=False, indent=2))

    print(f"\n{'OK' if ok == len(CASES) else 'CHECK'}: {ok}/{len(CASES)}")


if __name__ == "__main__":
    main()