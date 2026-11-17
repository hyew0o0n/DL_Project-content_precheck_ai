
"""W7 - 게시 예정일 및 특별한 날 안내"""

from datetime import date
import re


# 역사적·사회적 맥락에 대한 추가 검토가 필요한 날짜
SPECIAL_DAYS = {
    "03-01": "삼일절",
    "04-03": "제주4·3 희생자 추념일",
    "04-16": "세월호 참사일",
    "05-18": "5·18민주화운동 기념일",
    "06-06": "현충일",
    "06-25": "6·25전쟁일",
    "08-14": "일본군 위안부 피해자 기림의 날",
    "08-15": "광복절",
    "08-29": "경술국치일",
    "10-29": "이태원 참사일",
}

CAUTION_MESSAGE = (
    "역사적 맥락이나 부적절한 표현이 포함되지 않았는지 "
    "한 번 더 유의해 주세요."
)


def get_reference_date(post_date: str | None = None) -> date:
    """게시 예정일이 있으면 해당 날짜, 없으면 오늘 날짜를 반환한다."""

    if post_date is None or not post_date.strip():
        return date.today()

    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", post_date):
        raise ValueError(
            "게시 예정일은 YYYY-MM-DD 형식이어야 합니다."
        )

    return date.fromisoformat(post_date)


def check_special_day(ref_date: date) -> dict | None:
    """특별한 날이면 안내 정보, 일반 날짜면 None을 반환한다."""

    key = ref_date.strftime("%m-%d")
    name = SPECIAL_DAYS.get(key)

    if name is None:
        return None

    date_label = f"{ref_date.month}월 {ref_date.day}일"

    if ref_date == date.today():
        message = (
            f"오늘은 {date_label} {name}입니다. "
            f"{CAUTION_MESSAGE}"
        )
    else:
        message = (
            f"게시 예정일인 {date_label}은 {name}입니다. "
            f"{CAUTION_MESSAGE}"
        )

    return {
        "date": ref_date.isoformat(),
        "name": name,
        "message": message,
    }